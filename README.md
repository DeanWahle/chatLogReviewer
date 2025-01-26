# Chat Bot Log Analysis and Reporting

A tool designed to analyze and summarize customer service conversations from production logs. The tool automatically groups conversation logs, analyzes interactions for sentiment, pain points, successful exchanges, and patterns, and generates daily summary reports that can be sent via email.

## Features

- **Conversation Analysis**: Groups customer service logs into conversations based on user ID and timestamps.
- **Sentiment & Theme Detection**: Uses GPT-4 to analyze user interactions and detect sentiment, pain points, and recurring themes.
- **Daily Reports**: Generates a daily summary of the conversation logs and sends it via email in both text and PDF format.
- **Automated Log Collection**: Fetches logs from the Humanloop API and processes them automatically.
- **Customizable Email Reports**: Sends the final summary report to a designated email address.

## Installation

### 1. Clone the repository

Clone this repository to your local machine:

```bash
git clone https://github.com/DeanWahle/chatLogReviewer.git
cd chatLogReviewer
```

### 2. Set up the environment

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

### 3. Install dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Set environment variables

Create a `.env` file in the root of the repository and add the following environment variables:

```bash
OPENAI_API_KEY=your_openai_api_key
HUMANLOOP_API_KEY=your_humanloop_api_key
GMAIL_APP_PASSWORD=your_gmail_app_password
```

Replace the placeholder values with your actual API keys and Gmail app password.

## Usage

Run the script to fetch logs, process them, generate summaries, and send the reports:

```bash
python main.py
```

This will:

- Fetch production logs from the Humanloop API.
- Group logs into conversations.
- Analyze the conversations using GPT-4.
- Generate daily summaries and write them to a text file.
- Convert the summaries into a PDF.
- Email the PDF report to the specified email address.

The script runs on a daily schedule, so you can set it up to be triggered at 8 AM PST or any other time that suits your needs using scheduling tools like cron (Linux/Mac) or Task Scheduler (Windows).

## Contributing

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Commit your changes.
4. Push to your forked repository.
5. Create a pull request to the main repository.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
