Streamlit Cloud deployment guide

This repository is prepared to run on Streamlit Cloud. Follow these steps to deploy the app and (optionally) enable the chatbot once you've chosen a hosted LLM provider.

1) Connect repository to Streamlit Cloud
   - Sign in to https://streamlit.io/cloud with your GitHub account.
   - Create a new app and choose the repository `finance-tracker-dashboard` and the `main` branch.
   - Set the app's main file to `app.py` if prompted.

2) Runtime and requirements
   - runtime.txt is already present (Python 3.11).
   - requirements.txt contains the Python dependencies used by the app.
   - Streamlit Cloud will install these automatically during deployment.

3) Secrets (for future LLM/chatbot enablement)
   - The chatbot is currently disabled. To enable it later with a hosted provider, add the following secrets in the Streamlit Cloud dashboard (App Settings → Secrets):

     [secrets]
     llm_provider = "openai"        # provider string, e.g. "openai" or "anthropic"
     llm_api_key = "<YOUR_API_KEY>" # your provider API key
     # optional: other config such as model name or base url
     llm_model = "gpt-4o-mini"      # example default, optional

   - Alternatively add the same keys to a local `.streamlit/secrets.toml` file for local testing (do NOT commit your real keys to Git).

4) Environment
   - The app uses a zero-state by default. Uploaded statements are stored in the app's SQLite DB file (not committed to Git). On Streamlit Cloud, the file system is ephemeral — for persistent storage consider attaching an external DB or cloud storage.

5) App behavior notes
   - The chatbot page currently shows a "coming soon" placeholder — no external LLM calls are made.
   - When LLM secrets are provided the chatbot can be re-enabled by updating `pages/chatbot.py` to call the provider API.

6) Troubleshooting
   - If the app fails to start, check the deploy logs for a missing dependency or Python version mismatch.
   - If the chatbot fails after enabling LLM, verify the secrets and provider endpoint.

7) Security
   - Never commit API keys or secrets into the repository. Use Streamlit Secrets or environment variables.

If you'd like, I can also add a short GitHub Actions workflow to run basic linting/tests on pushes before deployment. Reply "add CI" to have that added.