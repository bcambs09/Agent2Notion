
# Notion API: Database Query Filter - The Filter Object

## Overview

When querying a Notion database, you can use a filter object in your request to limit the returned entries based on specified criteria. The filter object closely mimics the database filter option in the Notion UI.

## Example: Filtering by Checkbox Property

**cURL Example:**
```bash
curl -X POST 'https://api.notion.com/v1/databases/897e5a76ae524b489fdfe71f5945d1af/query' \
  -H 'Authorization: Bearer '"$NOTION_API_KEY"'' \
  -H 'Notion-Version: 2022-06-28' \
  -H "Content-Type: application/json" \
  --data '{
    "filter": {
      "property": "Task completed",
      "checkbox": {
        "equals": true
      }
    }
  }'
```

**JavaScript SDK Example:**
```js
const { Client } = require('@notionhq/client');
const notion = new Client({ auth: process.env.NOTION_API_KEY });
const databaseId = 'd9824bdc-8445-4327-be8b-5b47500af6ce';

const filteredRows = async () => {
  // Filter logic
};
```

## Structure of a Filter Object

A filter object contains these fields:

| Field     | Type   | Description                                                            | Example value             |
|-----------|--------|------------------------------------------------------------------------|--------------------------|
| property  | string | The name of the property as it appears in the database or property ID. | "Task completed"         |
| ...type   | object | The condition for the query; only types listed below are supported.     | "checkbox": { "equals": true } |

Supported property types include:
- checkbox
- date
- files
- formula
- multi_select
- number
- people
- phone_number
- relation
- rich_text
- select
- status
- timestamp
- ID

**Example checkbox filter object:**
```json
{
  "filter": {
    "property": "Task completed",
    "checkbox": {
      "equals": true
    }
  }
}
```

## Chained Filters (`and` / `or`)

Filters can be chained in `and` and `or` groups:

**Example Filter Object:**
```json
{
  "and": [
    {
      "property": "Done",
      "checkbox": {
        "equals": true
      }
    },
    {
      "or": [
        {
          "property": "Tags",
          "contains": "A"
        },
        {
          "property": "Tags",
          "contains": "B"
        }
      ]
    }
  ]
}
```

Single property filters are supported as well:
```json
{
  "property": "Done",
  "checkbox": {
    "equals": true
  }
}
```

## Filtering and Sorting Together

You can combine filters and sorts in the same request:
```json
{
  "filter": {
    "or": [
      {
        "property": "In stock",
        "checkbox": {
          "equals": true
        }
      },
      {
        "property": "Cost of next trip",
        "number": {
          "greater_than_or_equal_to": 2
        }
      }
    ]
  },
  "sorts": [
    {
      "property": "Last ordered",
      "direction": "ascending"
    }
  ]
}
