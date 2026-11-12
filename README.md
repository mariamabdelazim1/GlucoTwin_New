# GlucoTwin

GlucoTwin is organized as a monorepo. The website, patient mobile app, application API, and Python prediction service are versioned together but can be built and deployed independently.

## Repository layout

```text
apps/
  web/                 React and Vite website
  mobile/              Flutter patient application
services/
  api/                 Node.js authentication and synchronization API
  prediction/          Python GRU–Hovorka inference and bolus simulation code
packages/
  api-contract/        Shared, versioned API contract
docs/                  Architecture and project documentation
```

## Local development

Copy the local environment example and start PostgreSQL:

```bash
cp .env.example .env
docker compose up -d postgres
```

Install the Node workspaces, migrate the database, and explicitly seed development demo data:

```bash
npm install
npm run db:migrate
npm run db:seed
```

Run the API and website in separate terminals:

```bash
npm run dev:api
npm run dev:web
```

Run the Flutter application from `apps/mobile`:

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8787
```

The API requires PostgreSQL and fails clearly if `DATABASE_URL`, connectivity, or migrations are missing. It does not fall back to the former JSON store. The Python prediction service remains isolated from the clients; see `services/prediction/README.md` for its model contract and current status.

## Deployment

Configure each deployment with its own root directory:

- Website: `apps/web`
- Mobile build: `apps/mobile`
- Application API: `services/api`
- Prediction service: `services/prediction`

Keeping these projects in one repository does not require deploying them as one service.
