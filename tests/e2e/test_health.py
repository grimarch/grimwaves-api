import httpx


async def test_health_endpoint(base_url):
    """Test the health endpoint to ensure the API is accessible.

    This test verifies that the /health endpoint returns a 200 status code
    and the expected JSON response, indicating that the API is up and running.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
