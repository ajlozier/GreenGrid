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
3. Set **Authorization Callback Domain** to:
   - For local development: `localhost`
   - For production: your domain (e.g., `greengrid.yourdomain.com`)
4. Copy your **Client ID** and **Client Secret** to `secrets.py`

> **Note:** The callback domain should be just the domain, not a full URL. For example, use `localhost` not `http://localhost:5001`.

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
- ACM certificate for your domain (in the **same region** as deployment)

### Deployment Steps

```bash
# Set your AWS profile and region
export AWS_PROFILE=your-profile
export AWS_REGION=us-west-2

# 1. Create the ECS service-linked role (first time only, may already exist)
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com

# 2. Deploy the CloudFormation stack
aws cloudformation create-stack \
  --stack-name greengrid \
  --template-body file://cloudformation.yaml \
  --capabilities CAPABILITY_IAM \
  --region $AWS_REGION \
  --parameters \
    ParameterKey=DomainName,ParameterValue=greengrid.yourdomain.com \
    ParameterKey=HostedZoneId,ParameterValue=Z1234567890ABC \
    ParameterKey=CertificateArn,ParameterValue=arn:aws:acm:us-west-2:123456789:certificate/abc-123 \
    ParameterKey=StravaClientId,ParameterValue=12345 \
    ParameterKey=StravaClientSecret,ParameterValue=your-strava-secret \
    ParameterKey=DBPassword,ParameterValue=your-secure-db-password

# 3. Wait for stack creation (10-15 minutes)
aws cloudformation wait stack-create-complete --stack-name greengrid --region $AWS_REGION

# 4. Get the ECR repository name
ECR_REPO=$(aws ecr describe-repositories --region $AWS_REGION \
  --query 'repositories[?contains(repositoryName, `greengrid`)].repositoryUri' --output text)
echo "ECR Repository: $ECR_REPO"

# 5. Authenticate Docker with ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO

# 6. Build and push the Docker image
#    ⚠️ IMPORTANT: If you're on Apple Silicon (M1/M2/M3 Mac), you MUST specify the platform
docker build --platform linux/amd64 -t greengrid:latest .
docker tag greengrid:latest $ECR_REPO:latest
docker push $ECR_REPO:latest

# 7. Force ECS to deploy the new image
aws ecs update-service \
  --cluster greengrid-cluster \
  --service greengrid-service \
  --force-new-deployment \
  --region $AWS_REGION

# 8. Update Strava callback domain to your production domain in Strava API settings
```

### ⚠️ Apple Silicon (M1/M2/M3) Mac Users

ECS Fargate runs on x86_64 (AMD64) architecture. If you build on an Apple Silicon Mac without specifying the platform, you'll get:

```
exec /usr/local/bin/python: exec format error
```

**Always use `--platform linux/amd64`** when building for AWS:

```bash
docker build --platform linux/amd64 -t greengrid:latest .
```

### Updating the Application

After making code changes, rebuild and redeploy:

```bash
# Rebuild for AMD64 and push
docker build --platform linux/amd64 -t greengrid:latest .
docker tag greengrid:latest $ECR_REPO:latest
docker push $ECR_REPO:latest

# Force ECS to pull the new image
aws ecs update-service \
  --cluster greengrid-cluster \
  --service greengrid-service \
  --force-new-deployment \
  --region $AWS_REGION
```

### Troubleshooting AWS Deployment

**Check service status:**
```bash
aws ecs describe-services \
  --cluster greengrid-cluster \
  --services greengrid-service \
  --region $AWS_REGION \
  --query 'services[0].{Running:runningCount,Desired:desiredCount,Events:events[:5].message}'
```

**View container logs:**
```bash
# Get the latest log stream
LOG_STREAM=$(aws logs describe-log-streams \
  --log-group-name /ecs/greengrid \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --region $AWS_REGION \
  --query 'logStreams[0].logStreamName' --output text)

# View logs
aws logs get-log-events \
  --log-group-name /ecs/greengrid \
  --log-stream-name $LOG_STREAM \
  --region $AWS_REGION \
  --query 'events[*].message' --output text
```

**Check task status:**
```bash
# List running tasks
aws ecs list-tasks \
  --cluster greengrid-cluster \
  --service-name greengrid-service \
  --region $AWS_REGION

# Describe a specific task
aws ecs describe-tasks \
  --cluster greengrid-cluster \
  --tasks <task-id> \
  --region $AWS_REGION \
  --query 'tasks[0].{Status:lastStatus,StopReason:stoppedReason}'
```

**Common issues:**

| Error | Cause | Solution |
|-------|-------|----------|
| `exec format error` | Built on ARM Mac, running on x86_64 | Use `--platform linux/amd64` |
| `CannotPullContainerError` | Image not in ECR | Push image to ECR first |
| `relation "greens" does not exist` | Old image without auto-migration | Rebuild and push latest code |
| `AccessUnauthorized` from Strava | Wrong credentials or callback domain | Check Strava API settings |

### CloudFormation Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `DomainName` | Full domain name (e.g., `greengrid.example.com`) | Yes |
| `HostedZoneId` | Route53 Hosted Zone ID | Yes |
| `CertificateArn` | ACM certificate ARN for HTTPS (must be in same region) | Yes |
| `StravaClientId` | Strava API Client ID | Yes |
| `StravaClientSecret` | Strava API Client Secret | Yes |
| `DBPassword` | PostgreSQL password (min 8 characters) | Yes |
| `FlaskSecretKey` | Flask session secret (auto-generated if not provided) | No |

### Database Initialization

The database table is automatically created when the application starts. No manual SQL execution is required. The app runs `db.create_all()` on startup to ensure the `greens` table exists.

### Strava API Configuration

After deploying to AWS, update your Strava API settings:

1. Go to [Strava API Settings](https://www.strava.com/settings/api)
2. Set **Authorization Callback Domain** to your production domain (e.g., `greengrid.yourdomain.com`)
   - Do NOT include `https://` or any path
   - Just the domain name

### Estimated AWS Costs

~$30-50/month breakdown:
- RDS db.t3.micro: ~$15/month
- NAT Gateway: ~$10-15/month (consider removing for cost savings)
- ALB: ~$5/month
- ECS Fargate: ~$5-10/month (depends on usage)
- Route53: ~$0.50/month

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

## Credits

This project is a fork and extension of [How Many Greens](https://strava.mack.im/) created by **Mack Goodstein** ([@mackmgg](https://github.com/mackmgg)).

- Original application: [strava.mack.im](https://strava.mack.im/)
- Original repository: [github.com/mackmgg/StravaCounting](https://github.com/mackmgg/StravaCounting)

The Grid tracking feature and Docker/AWS deployment were added to extend the original summit counter with the unique Boulder tradition of "gridding" Green Mountain.

## License

MIT

---

*Powered by Strava*
