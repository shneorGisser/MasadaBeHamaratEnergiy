# העלאה לאוויר — Google Cloud Run (+ Cloud SQL)

**למה לא Google AI Studio:** מצב Build ב-AI Studio מריץ רק Frontend של React עם שרת Node.js.
אין בו Python, ולכן אין FastAPI ואין את הפותר. בנוסף, ה-SQLite המקומי נמחק בכל פריסה מחדש.
AI Studio מתאים לאב-טיפוס של העיצוב בלבד. השרת האמיתי עולה ל-Cloud Run.

## מה נבדק בפועל ומה לא
| נבדק | תוצאה |
|---|---|
| התקנת ה-backend כחבילה רגילה (כמו בקונטיינר) והרצת מיגרציות, סימולציה ודו״ח | עבר |
| כל 98 בדיקות ה-backend מול PostgreSQL 16 אמיתי (`VEL_TEST_PG_URL`) | עבר |
| שרת FastAPI שמגיש את ה-build של ה-frontend (זה מה שרץ בבדיקות ה-E2E) | עבר |
| `docker build` | **לא נבדק:** Docker Hub חסום בסביבת העבודה שלי. צריך להריץ אצלך או ב-Cloud Build |
| פריסה בפועל ל-Cloud Run | **לא בוצעה:** דורשת את חשבון ה-Google Cloud שלך |

## 1. הכנה (פעם אחת)
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
REGION=me-west1   # תל אביב
```

## 2. מסד נתונים (Cloud SQL for PostgreSQL)
```bash
gcloud sql instances create vel-db --database-version=POSTGRES_16 \
  --tier=db-f1-micro --region=$REGION --edition=ENTERPRISE
gcloud sql databases create vel --instance=vel-db
gcloud sql users create vel --instance=vel-db --password='CHOOSE_A_STRONG_PASSWORD'
INSTANCE=$(gcloud sql instances describe vel-db --format='value(connectionName)')
printf 'postgresql+psycopg://vel:CHOOSE_A_STRONG_PASSWORD@/vel?host=/cloudsql/%s' "$INSTANCE" | \
  gcloud secrets create vel-database-url --data-file=-
```
עלות: db-f1-micro עולה בערך 8$ לחודש. אין לו Free Tier, והוא לא מכוסה ב-SLA.

## 3. פריסה
```bash
gcloud run deploy virtual-energy-lab --source . --region=$REGION \
  --add-cloudsql-instances=$INSTANCE \
  --set-secrets=VEL_DATABASE_URL=vel-database-url:latest \
  --memory=1Gi --cpu=1 --min-instances=0 --max-instances=1 \
  --allow-unauthenticated
```
* המיגרציות (Alembic) רצות אוטומטית כשהשרת עולה. לכן `--max-instances=1` בפריסה הראשונה, כדי שלא ירוצו שני מופעים במקביל על אותו מסד. אחרי שהמסד מאותחל אפשר להעלות את המספר.
* Cloud Run בחיוב לפי בקשות: 180,000 vCPU-שניות ו-2 מיליון בקשות בחודש חינם, עם חשבון חיוב פעיל. מומלץ להגדיר התראת תקציב.
* **PDF של הדו״ח:** בקונטיינר אין Chromium, ולכן `/api/reports/{id}/pdf` מחזיר 501. אפשר להדפיס או לשמור כ-PDF מהדפדפן. כדי לאפשר PDF בשרת, מוסיפים `apt-get install chromium` לשלב ה-runtime (בערך 300MB) ומגדירים `VEL_CHROMIUM=/usr/bin/chromium`.

### חלופת הדגמה (בלי Cloud SQL)
SQLite על Cloud Storage volume mount עם `--max-instances=1`. Cloud Storage FUSE לא נועל קבצים, ולכן הדרך הזו מתאימה להדגמה בלבד, לא לכיתה שלמה.

## 4. דומיין משלך
Firebase Hosting עם rewrite ל-Cloud Run (`"run": {"serviceId": "virtual-energy-lab", "region": "me-west1"}`) נותן SSL מנוהל על הדומיין שלך. אפשר גם להשתמש ב-domain mapping של Cloud Run.

## 5. לפני שפותחים לסטודנטים
* אין עדיין התחברות משתמשים. כל מי שיש לו את הקישור רואה את כל הפרויקטים. לכיתה אמיתית צריך להוסיף אימות (שלב עתידי).
* גיבוי: גיבויים אוטומטיים של Cloud SQL, וגם "ייצוא גיבוי" (JSON) לכל פרויקט מתוך האפליקציה.
