# 🏔️ Green Grid

A web application that tracks Green Mountain (Boulder, CO) summit counts using Strava data, with a unique "Grid" progress tracker.

## What is "Gridding"?

Gridding is a Boulder community tradition where athletes aim to summit Green Mountain on every unique day of the year (366 days including Feb 29). The Grid tracks your progress toward completing all 366 calendar days, which typically takes several years of dedication.

## Features

- **Summit Counter**: Tracks total Green Mountain summits from your Strava activities
- **Grid Progress**: Shows how many unique days of the year you've summited (X/366)
- **Leaderboard**: Compare your stats with other athletes
- **Beautiful UI**: Modern dark theme with progress visualization

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [Strava API Application](https://www.strava.com/settings/api) credentials

## Configuration

Create a `secrets.py` file in the project root:

```python
client_id = 12345                          # Your Strava API Client ID (integer)
api_key = 'your-strava-client-secret'      # Your Strava Client Secret
secret_key = 'random-flask-session-key'    # Any random string for Flask sessions
default_url = 'http://localhost:5001'      # Your app URL
```

### Strava API Setup

1. Go to [Strava API Settings](https://www.strava.com/settings/api)
2. Create an application (or use existing)
3. Set **Authorization Callback Domain** to: `localhost`
4. Copy your **Client ID** and **Client Secret** to `secrets.py`

## Local Development with Docker

### Start the Application

```bash
docker compose up --build
```

The app will be available at **http://localhost:5001**

### Other Commands

```bash
# Run in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Stop and remove database volume (fresh start)
docker compose down -v
```

## AWS Deployment

The included CloudFormation template deploys a production-ready infrastructure:

| Component | Service |
|-----------|---------|
| Compute | ECS Fargate (serverless containers) |
| Database | RDS PostgreSQL |
| Load Balancer | Application Load Balancer with HTTPS |
| DNS | Route53 |
| Secrets | AWS Secrets Manager |
| Container Registry | ECR |

### Prerequisites for AWS

- AWS CLI configured with appropriate permissions
- Route53 hosted zone for your domain
- ACM certificate for your domain (in the same region)

### Deployment Steps

```bash
# 1. Create the ECS service-linked role (first time only)
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com

# 2. Deploy the CloudFormation stack
aws cloudformation create-stack \
  --stack-name greengrid \
  --template-body file://cloudformation.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters \
    ParameterKey=DomainName,ParameterValue=greengrid.yourdomain.com \
    ParameterKey=HostedZoneId,ParameterValue=Z1234567890ABC \
    ParameterKey=CertificateArn,ParameterValue=arn:aws:acm:us-east-1:123456789:certificate/abc-123 \
    ParameterKey=StravaClientId,ParameterValue=12345 \
    ParameterKey=StravaClientSecret,ParameterValue=your-strava-secret \
    ParameterKey=DBPassword,ParameterValue=your-secure-db-password

# 3. Wait for stack creation (10-15 minutes)
aws cloudformation wait stack-create-complete --stack-name greengrid

# 4. Get the ECR repository URI
ECR_URI=$(aws cloudformation describe-stacks --stack-name greengrid \
  --query 'Stacks[0].Outputs[?OutputKey==`ECRRepositoryURI`].OutputValue' --output text)

# 5. Build and push the Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URI
docker build -t greengrid .
docker tag greengrid:latest $ECR_URI:latest
docker push $ECR_URI:latest

# 6. Deploy to ECS
aws ecs update-service --cluster greengrid-cluster --service greengrid-service --force-new-deployment

# 7. Update Strava callback domain to your production domain
```

### CloudFormation Parameters

| Parameter | Description |
|-----------|-------------|
| `DomainName` | Full domain name (e.g., `greengrid.example.com`) |
| `HostedZoneId` | Route53 Hosted Zone ID |
| `CertificateArn` | ACM certificate ARN for HTTPS |
| `StravaClientId` | Strava API Client ID |
| `StravaClientSecret` | Strava API Client Secret |
| `FlaskSecretKey` | Flask session secret (optional, auto-generated) |
| `DBPassword` | PostgreSQL password (min 8 characters) |

### Estimated AWS Costs

~$30-50/month (primarily RDS db.t3.micro + NAT Gateway)

## Project Structure

```
├── app.py                 # Flask application
├── cloudformation.yaml    # AWS infrastructure template
├── docker-compose.yml     # Local Docker orchestration
├── Dockerfile             # Container image definition
├── init.sql               # Database initialization script
├── requirements.txt       # Python dependencies
├── secrets.py             # Local configuration (not in git)
├── favicon.ico            # Site icon
├── media/                 # Static assets (Strava branding)
└── templates/             # Jinja2 HTML templates
    └── index.html         # Main page template
```

## Environment Variables

The app supports both `secrets.py` (local) and environment variables (production):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `DEFAULT_URL` | Application base URL |
| `STRAVA_CLIENT_ID` | Strava API Client ID |
| `STRAVA_CLIENT_SECRET` | Strava API Client Secret |
| `FLASK_SECRET_KEY` | Flask session encryption key |
| `SILENCE_TOKEN_WARNINGS` | Set to `true` to suppress stravalib warnings |

## Database Schema

```sql
CREATE TABLE greens (
    id INTEGER PRIMARY KEY,        -- Strava athlete ID
    name VARCHAR(255),             -- Athlete name
    num INTEGER DEFAULT 0,         -- Total summit count
    grid_count INTEGER DEFAULT 0,  -- Unique days summited (0-366)
    lastupdate TIMESTAMP           -- Last data refresh
);
```

## How It Works

1. User authenticates with Strava OAuth
2. App fetches segment efforts for Green Mountain summit segments
3. Total efforts are counted for the summit count
4. Effort dates are analyzed to find unique (month, day) combinations for the grid
5. Data is stored in PostgreSQL and displayed on the leaderboard

### Tracked Segments

The app tracks these Strava segments that represent Green Mountain summits:
- `30545810`, `30546062`, `30546055`, `7492562`

## License

MIT

---

*Powered by Strava*
