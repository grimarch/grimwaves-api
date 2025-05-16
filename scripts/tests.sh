#!/bin/bash

# Базовые настройки
BASE_URL="https://api.grimwaves.local"
MAX_RETRIES=30
RETRY_DELAY=2

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Функция для форматированного вывода результатов
print_result() {
    local test_name=$1
    local command=$2
    local start_time=$(date +%s.%N)
    
    echo -e "\n${YELLOW}=== $test_name ===${NC}"
    echo "Команда: $command"
    echo "Результат:"
    
    # Выполняем команду и сохраняем результат
    local result=$(eval "$command")
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $start_time" | bc)
    
    echo "$result"
    echo -e "${YELLOW}Время выполнения: ${duration} сек${NC}"
    echo "=================="
    
    # Возвращаем результат для дальнейшей обработки
    echo "$result"
}

# Функция для извлечения task_id из ответа
extract_task_id() {
    local response=$1
    echo "$response" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4
}

# Функция для проверки статуса задачи
check_task_status() {
    local task_id=$1
    local retries=0
    
    echo -e "${YELLOW}Проверяем статус задачи: $task_id${NC}"
    
    while [ $retries -lt $MAX_RETRIES ]; do
        local status_response=$(curl -k -s "${BASE_URL}/music/release_metadata/${task_id}")
        local status=$(echo "$status_response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        
        echo -e "Статус: $status"
        
        if [ "$status" = "completed" ]; then
            echo -e "${GREEN}Задача завершена успешно!${NC}"
            echo "$status_response"
            return 0
        elif [ "$status" = "failed" ]; then
            echo -e "${RED}Задача завершилась с ошибкой!${NC}"
            echo "$status_response"
            return 1
        fi
        
        retries=$((retries + 1))
        echo "Ожидаем $RETRY_DELAY секунд... (попытка $retries из $MAX_RETRIES)"
        sleep $RETRY_DELAY
    done
    
    echo -e "${RED}Превышено время ожидания!${NC}"
    return 1
}

# Функция для проверки доступности сервисов
check_services() {
    echo -e "${YELLOW}Проверка доступности сервисов...${NC}"
    
    # Проверка API через Traefik
    curl -k -s "${BASE_URL}/health" > /dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}API доступен${NC}"
    else
        echo -e "${RED}API недоступен${NC}"
        exit 1
    fi
    
    # Проверка Redis через Python
    docker exec grimwaves-api python3 -c "
import redis
from grimwaves_api.core.settings import settings
r = redis.from_url(settings.redis_url)
assert r.ping()
" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Redis доступен${NC}"
    else
        echo -e "${RED}Redis недоступен${NC}"
        exit 1
    fi
    
    # Проверка Celery
    docker exec grimwaves-celery-worker celery -A grimwaves_api.core.celery_app inspect ping > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Celery worker доступен${NC}"
    else
        echo -e "${RED}Celery worker недоступен${NC}"
        exit 1
    fi
}

# Функция для запуска теста с проверкой статуса
run_test_with_status() {
    local test_name=$1
    local payload=$2
    
    echo -e "\n${YELLOW}Запускаем тест: $test_name${NC}"
    
    local response=$(curl -k -s -X POST "${BASE_URL}/music/release_metadata" \
        -H "Content-Type: application/json" \
        -H "Origin: https://grimwaves.local" \
        -d "$payload")
    
    echo "Ответ API:"
    echo "$response"
    
    local task_id=$(extract_task_id "$response")
    
    if [ -n "$task_id" ]; then
        check_task_status "$task_id"
    else
        echo -e "${RED}Не удалось получить task_id из ответа${NC}"
        echo "Ответ API:"
        echo "$response"
    fi
}

# Запуск всех тестов
echo -e "${YELLOW}Начинаем тестирование API${NC}"

# Проверка сервисов
check_services

# Тест 1: Валидный запрос
run_test_with_status "Тест 1: Валидный запрос" '{
    "band_name": "Gojira",
    "release_name": "Fortitude",
    "country_code": "FR"
}'

# Тест 2: Кэширование
echo -e "\n${YELLOW}=== Тестирование кэширования ===${NC}"
# Первый запрос
start_time=$(date +%s.%N)
run_test_with_status "Тест кэширования (первый запрос)" '{
    "band_name": "Metallica",
    "release_name": "Master of Puppets",
    "country_code": "US"
}'
first_duration=$(echo "$(date +%s.%N) - $start_time" | bc)

# Небольшая пауза
sleep 2

# Повторный запрос
start_time=$(date +%s.%N)
run_test_with_status "Тест кэширования (повторный запрос)" '{
    "band_name": "Metallica",
    "release_name": "Master of Puppets",
    "country_code": "US"
}'
second_duration=$(echo "$(date +%s.%N) - $start_time" | bc)

echo -e "${YELLOW}Результаты теста кэширования:${NC}"
echo "Время первого запроса: $first_duration сек"
echo "Время повторного запроса: $second_duration сек"

# Тест 3: Невалидные данные
print_result "Тест 3.1: Пустые поля" "curl -k -s -X POST '${BASE_URL}/music/release_metadata' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://grimwaves.local' \
  -d '{
    \"band_name\": \"\",
    \"release_name\": \"\",
    \"country_code\": \"US\"
  }'"

print_result "Тест 3.2: Невалидный country_code" "curl -k -s -X POST '${BASE_URL}/music/release_metadata' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://grimwaves.local' \
  -d '{
    \"band_name\": \"Metallica\",
    \"release_name\": \"Master of Puppets\",
    \"country_code\": \"XX\"
  }'"

# Тест 4: Специальные случаи
print_result "Тест 4.1: Специальные символы" "curl -k -s -X POST '${BASE_URL}/music/release_metadata' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://grimwaves.local' \
  -d '{
    \"band_name\": \"AC/DC\",
    \"release_name\": \"Back in Black (Deluxe Edition)\",
    \"country_code\": \"US\"
  }'"

print_result "Тест 4.2: Несуществующий релиз" "curl -k -s -X POST '${BASE_URL}/music/release_metadata' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://grimwaves.local' \
  -d '{
    \"band_name\": \"NonExistentArtist123\",
    \"release_name\": \"NonExistentRelease456\",
    \"country_code\": \"US\"
  }'"

print_result "Тест 4.3: Несуществующий task_id" "curl -k -s -X GET '${BASE_URL}/music/release_metadata/non_existent_task_id'"

# Тест 5: Мультиязычные запросы
print_result "Тест 5.1: Кириллица" "curl -k -s -X POST '${BASE_URL}/music/release_metadata' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://grimwaves.local' \
  -d '{
    \"band_name\": \"Кино\",
    \"release_name\": \"Группа крови\",
    \"country_code\": \"RU\"
  }'"

print_result "Тест 5.2: Японский" "curl -k -s -X POST '${BASE_URL}/music/release_metadata' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://grimwaves.local' \
  -d '{
    \"band_name\": \"椎名林檎\",
    \"release_name\": \"無罪モラトリアム\",
    \"country_code\": \"JP\"
  }'"

echo -e "\n${GREEN}Тестирование завершено!${NC}"
