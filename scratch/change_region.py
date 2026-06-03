"""Change Railway deployment region to US West."""
import urllib.request
import json

TOKEN = "JQU8KUHQy4fWW3W5kQeQGzXIIybUCE2MRcc0S3F0IGU"
SERVICE_ID = "64bfc571-cc26-43e4-911a-24ddcd90f466"
ENV_ID = "6693f792-fb48-4cec-8832-539908aaa511"

def gql(query_str):
    req = urllib.request.Request(
        "https://backboard.railway.app/graphql/v2",
        data=json.dumps({"query": query_str}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}")
        return None

# Query available regions
result = gql("{ regions { name id } }")
print("Available regions:", json.dumps(result, indent=2) if result else "Failed")