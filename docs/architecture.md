# Architecture

```text
React website ----\
                   >---- Node application API ---- PostgreSQL
Flutter mobile ---/              |
                                  +---- private Python prediction service
```

The web and mobile clients communicate only with the application API. The application API owns authentication, authorization, persistence, and audit records. It calls the private Python service for physiological parameter inference, glucose trajectory simulation, and experimental bolus candidate evaluation.

PostgreSQL stores original patient events independently of the training-data layout. Prediction and recommendation tables provide provenance-ready storage, but the application API does not yet expose endpoints that create authoritative AI output. The next model-integration step is a private authenticated service-to-service path that writes those records transactionally after Python inference succeeds.

Model artifacts and Python dependencies must never be shipped in the React or Flutter bundles.
