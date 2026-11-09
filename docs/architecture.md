# Architecture

```text
React website ----\
                   >---- Node application API ---- database
Flutter mobile ---/              |
                                  +---- private Python prediction service
```

The web and mobile clients communicate only with the application API. The application API owns authentication, authorization, persistence, and audit records. It calls the private Python service for physiological parameter inference, glucose trajectory simulation, and experimental bolus candidate evaluation.

Model artifacts and Python dependencies must never be shipped in the React or Flutter bundles.
