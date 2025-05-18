```mermaid
graph TD
    A[API Request Received (NL Input)] --> B{Interpret User Intent};
    B -- Needs Schema Info? --> C{Fetch Notion Schema?};
    B -- Needs to Find Data? --> E{Search Notion Data?};
    B -- Clear Actionable Plan --> G{Formulate Notion API Plan};

    C -- Yes --> D[Fetch Notion DB/Page Schema];
    C -- No --> E;
    D --> E;

    E -- Yes --> F[Search Notion for Relevant Data];
    E -- No --> G;
    F --> G;

    G --> H[Execute Notion API Calls];
    H --> I{API Call Succeeded?};

    I -- Yes --> K[Format Success Response];
    I -- No --> J[Handle API Error/Retry];

    J -- Retry Possible --> G;
    J -- No Retry / Max Retries --> L[Format Error Response];

    K --> M[API Response Sent];
    L --> M;
``` 