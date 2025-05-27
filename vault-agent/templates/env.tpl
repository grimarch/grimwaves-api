{{ with secret "secret/data/grimwaves-api/dev/streaming/spotify" -}}
SPOTIFY_CLIENT_ID="{{ .Data.data.client_id }}"
SPOTIFY_CLIENT_SECRET="{{ .Data.data.client_secret }}"
{{ end }}
{{ with secret "secret/data/grimwaves-api/dev/config" -}}
CELERY_BROKER_URL="{{ .Data.data.CELERY_BROKER_URL }}"
CELERY_RESULT_BACKEND="{{ .Data.data.CELERY_RESULT_BACKEND }}"
REDIS_URL="{{ .Data.data.REDIS_URL }}"
{{ end }} 
