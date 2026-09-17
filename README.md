# Personal Finance Statement Analyzer

This project is a local finance dashboard that allows a user to upload statement files in Excel or PDF format and receive:

- monthly expenditure summaries
- category-wise spending breakdowns
- money borrowed vs money lent tracking
- transaction previews for review
- a dedicated placeholder area for future chatbot support

## Run locally

1. Open a terminal in the project folder.
2. Install dependencies:
   python -m pip install -r requirements.txt
3. Start the app:
   streamlit run app.py
4. Open the local URL shown in the terminal, usually:
   http://localhost:8501

## Included sample data

The project includes a sample CSV file in `sample_data/sample_transactions.csv` so the dashboard can be tested immediately without uploading a real statement.

## Supported file types

- CSV
- Excel (.xlsx, .xls)
- PDF (basic extraction for common statement layouts)

## Future enhancement

The UI already includes a reserved chatbot panel so future conversational finance support can be added without reworking the page layout.
