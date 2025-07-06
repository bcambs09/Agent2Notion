from main import app
import json

# Generate OpenAPI schema
openapi_schema = app.openapi()

# Save to file
with open("openapi.json", "w") as f:
    json.dump(openapi_schema, f, indent=2)

print("OpenAPI specification has been generated and saved to openapi.json") 