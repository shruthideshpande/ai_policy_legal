# Step-by-Step Deployment to Cloud Run

Now, follow these instructions from your terminal to deploy and run the crawler. Make sure you are in the `/home/shruthi6888/crawler/` directory.

## Step 1: Set Up Your GCP Environment

First, set some environment variables to make the following commands easier. Replace `"aipolicylegal"` with your actual GCP Project ID if it's different.

```bash
export PROJECT_ID="aipolicylegal"
export REGION="asia-south1" # Mumbai (asia-south1), Delhi (asia-south2)
export BUCKET_NAME="indiacode-pdfs-v1"
export JOB_NAME="indiacode-crawler-job"

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION
```

## Step 2: Enable Required GCP APIs

This command ensures the necessary services are enabled for your project.

```bash
gcloud services enable run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

## Step 3: Create the repository
```bash
gcloud artifacts repositories create cloud-run-source-deploy \
    --repository-format=docker \
    --location=$REGION \
    --description="Repository for Cloud Run source deployments"
```
    
## Step 4: Build and Submit the Container Image

This single command will:

1.  Package your code (respecting `.gcloudignore`).
2.  Send it to Google Cloud Build.
3.  Build the container image using your `Dockerfile`.
4.  Push the resulting image to Google Artifact Registry.

```bash
gcloud builds submit --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${JOB_NAME}"
```

## Step 5: Create the Cloud Run Job

This command creates the job definition in Cloud Run. It doesn't run it yet.

*   `--image`: Specifies the container image we just built.
*   `--set-env-vars`: Sets the environment variables your Python script will use. Set `DRY_RUN=false` to actually download PDFs.
*   `--task-timeout`: Sets the maximum run time. The default is 10 minutes. We'll set it to 10 hours (`36000s`). The maximum is 24 hours.
*   `--service-account`: It's a best practice to specify the service account. The default compute service account works fine if it has "Storage Admin" permissions.

To create a job for the first time, run the command below.  Use "update" instead of 
"create" to update an existing job.

```bash
gcloud beta run jobs create $JOB_NAME \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${JOB_NAME}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars="GCS_BUCKET_NAME=${BUCKET_NAME}" \
  --set-env-vars="DRY_RUN=false" \
  --task-timeout=36000
```
*(Note: You may be prompted to grant the Cloud Run service account permissions on the bucket. Ensure it has the "Storage Admin" role for full access.)*

## Step 6: Execute the Job

Now, you can manually trigger a run of your crawler job.

```bash
gcloud beta run jobs execute $JOB_NAME
```
You can monitor the progress of the job execution in the Google Cloud Console under "Cloud Run Jobs" or by viewing its logs. Each time you run this command, it will start a new crawl, which will load the `visited_urls.txt` from your GCS bucket and pick up where it left off.

You have now successfully containerized your crawler and can run it on-demand as a serverless job!