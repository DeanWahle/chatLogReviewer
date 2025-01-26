import json
import openai
import logging
import backoff
from typing import Dict, List, Tuple
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from humanloop import Humanloop
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from textwrap import wrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_conversation_prompt(conversations: Dict) -> str:
    formatted_convs = []
    for conv_id, messages in conversations.items():
        conv = [f"\nConversation {conv_id}:"]
        for msg in messages:
            conv.extend([
                f"User ({msg['log_id']}): {msg['input']}", 
                f"System: {msg['output']}\n"
            ])
        formatted_convs.append("\n".join(conv))
    
    prompt = """Analyze these customer service conversations. For each point, include SPECIFIC examples with their exact log_ids (format: log_XYZ):

1. Successful interactions
2. User pain points/frustrations 
3. Common themes/patterns
4. Overall user sentiment

IMPORTANT: Always reference specific log_ids when providing examples, not conversation numbers.

Conversations:
{}""".format("\n".join(formatted_convs))
    
    return prompt

@backoff.on_exception(
   backoff.expo,
   (openai.APIError, openai.RateLimitError),
   max_tries=5
)
def analyze_batch(conversations: Dict, client) -> Tuple[str, List[str]]:
   try:
       print(f"\nAnalyzing batch of {len(conversations)} conversations...")
       prompt = create_conversation_prompt(conversations)
       response = client.chat.completions.create(
           model="gpt-4",
           messages=[{"role": "user", "content": prompt}],
           temperature=0,
           timeout=30
       )
       print("Batch analysis successful")
       return response.choices[0].message.content, []
   except (openai.Timeout, TimeoutError) as e:
       print(f"\nERROR: API timeout - splitting batch")
       logger.error(f"Timeout: {e}")
       items = list(conversations.items())
       mid = len(items) // 2
       if mid == 0:
           return None, [f"Skipped conversation: {list(conversations.keys())[0]}"]
       return batch_analyze(dict(items[:mid]), 1)[0], batch_analyze(dict(items[mid:]), 1)[0]
   except Exception as e:
       print(f"\nERROR: {str(e)}")
       logger.error(f"Unexpected error: {e}")
       return None, [f"Error processing batch: {str(e)}"]

def batch_analyze(conversations: Dict, batch_size: int = 5) -> Tuple[List[str], List[str]]:
    print(f"\nStarting analysis of {len(conversations)} conversations in batches of {batch_size}")
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    summaries = []
    errors = []
    
    items = list(conversations.items())
    for i in range(0, len(items), batch_size):
        batch = dict(items[i:i + batch_size])
        summary, batch_errors = analyze_batch(batch, client)
        if summary:
            print(f"Successfully processed batch {i//batch_size + 1}")
            summaries.append(summary)
        if batch_errors:
            print(f"Encountered errors in batch {i//batch_size + 1}")
        errors.extend(batch_errors)
    
    print(f"\nAnalysis complete. Generated {len(summaries)} summaries with {len(errors)} errors")
    return summaries, errors

def get_production_logs(humanloop_client, file_id: str):
    yesterday = datetime.now(timezone.utc) - timedelta(days=2)
    logs = []
    
    print("Fetching logs from the last 24 hours...")
    for log in humanloop_client.logs.list(file_id=file_id, start_date=yesterday):
        if log.source == 'production':
            logs.append({
                'log_id': log.log_id,
                'created_at': log.created_at,
                'user': log.user,
                'input': log.inputs.get('user_message', ''),
                'output': log.output
            })
    print(f"Found {len(logs)} production logs")
    return logs

def group_conversations(logs: List[Dict], hour_window: int = 1) -> Dict:
    conversations = defaultdict(list)
    sorted_logs = sorted(logs, key=lambda x: x['created_at'])
    
    for log in sorted_logs:
        user_id = log['user']
        created_at = datetime.fromisoformat(str(log['created_at']).replace('Z', '+00:00'))
        
        # Find or create conversation group
        conv_found = False
        for conv_id, conv_logs in conversations.items():
            if (user_id == conv_logs[0]['user'] and 
                (created_at - datetime.fromisoformat(str(conv_logs[-1]['created_at']).replace('Z', '+00:00'))).total_seconds() <= hour_window * 3600):
                conversations[conv_id].append(log)
                conv_found = True
                break
                
        if not conv_found:
            conv_id = f"conv_{len(conversations) + 1}"
            conversations[conv_id] = [log]
    
    print(f"Grouped into {len(conversations)} conversations")
    return conversations

def write_summaries_to_file(summaries: List[str], errors: List[str]):
    filename = f"{datetime.now().strftime('%Y-%m-%d')}_log_summary.txt"
    
    mode = 'a' if os.path.exists(filename) else 'w'
    with open(filename, mode) as f:
        if mode == 'w':
            f.write(f"Log Analysis Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for i, summary in enumerate(summaries, 1):
            f.write(f"Batch {i} Analysis:\n{summary}\n\n")
            
        if errors:
            f.write("\nErrors:\n")
            for error in errors:
                f.write(f"- {error}\n")

def generate_final_summary(filename: str, client) -> str:
    with open(filename, 'r') as f:
        content = f.read()

    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    prompt = f"""Create a consolidated analysis report aggregating findings across all batches. Use this structure with clear spacing:

LOG ANALYSIS REPORT - {current_date}

SUCCESSFUL INTERACTIONS
[Aggregate unique successful interactions across all batches, with log IDs]
[2 blank lines]

USER PAIN POINTS/FRUSTRATIONS 
[Aggregate unique pain points across all batches, with log IDs]
[2 blank lines]

COMMON THEMES/PATTERNS
[List major recurring themes and patterns identified across all batches]
[2 blank lines]

USER SENTIMENT SUMMARY
[Overall sentiment analysis aggregated from all batches]
[2 blank lines]
- In the user senitiment summary section, rememeber that you can aggregate the sentiment across all batches, so it should only be one bullet with a few sentences.

Key guidelines:
- Avoid redundant examples across sections
- Include log IDs for all specific examples
- Group similar findings together
- Add a blank line between each bullet point

YOU MUST INCLUDE ALL SECTIONS - DO NOT SKIP ANY

Content to analyze:
{content}"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return response.choices[0].message.content

def write_to_pdf(final_summary: str, filename: str):
    pdf_filename = filename
    c = canvas.Canvas(pdf_filename, pagesize=letter)
    width, height = letter
    y = height - 40
    margin = 40
    line_height = 14
    section_spacing = line_height * 2

    def wrap_text(text, width):
        words = text.split()
        lines = []
        current_line = []
        current_width = 0

        for word in words:
            word_width = c.stringWidth(word, "Helvetica", 11)
            if current_width + word_width <= width:
                current_line.append(word)
                current_width += word_width + c.stringWidth(' ', "Helvetica", 11)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width

        if current_line:
            lines.append(' '.join(current_line))
        return lines

    def find_log_ids(text):
        import re
        matches = re.finditer(r'(log_[a-zA-Z0-9]+)', text)
        return [(m.group(1), m.start(), m.end()) for m in matches]

    for line in final_summary.split('\n'):
        if y < margin:
            c.showPage()
            y = height - margin

        if line.isupper() and len(line) > 3:
            c.setFont("Helvetica-Bold", 14)
            y -= section_spacing
            wrapped = wrap_text(line, width - 2*margin)
        else:
            c.setFont("Helvetica", 11)
            indent = 60 if line.strip().startswith('-') else margin
            wrapped = wrap_text(line, width - indent - margin)

        for wrapped_line in wrapped:
            if y < margin:
                c.showPage()
                y = height - margin

            x = indent if line.strip().startswith('-') else margin

            # Handle hyperlinks for log IDs
            log_ids = find_log_ids(wrapped_line)
            if log_ids:
                current_x = x
                last_end = 0
                for log_id, start, end in log_ids:
                    # Draw text before log ID
                    prefix = wrapped_line[last_end:start]
                    c.drawString(current_x, y, prefix)
                    current_x += c.stringWidth(prefix, "Helvetica", 11)

                    # Draw log ID as hyperlink
                    url = f"https://YOUR_HUMANLOOP_URL/logs?id={log_id}"  # Masked
                    log_text = wrapped_line[start:end]
                    c.setFillColorRGB(0, 0, 1)  # Blue color for links
                    c.drawString(current_x, y, log_text)

                    # Add hyperlink
                    rect = (current_x, y - 2, current_x + c.stringWidth(log_text, "Helvetica", 11), y + 10)
                    c.linkURL(url, rect)

                    current_x += c.stringWidth(log_text, "Helvetica", 11)
                    last_end = end
                    c.setFillColorRGB(0, 0, 0)  # Reset to black

                # Draw remaining text after last log ID
                if last_end < len(wrapped_line):
                    c.drawString(current_x, y, wrapped_line[last_end:])
            else:
                c.drawString(x, y, wrapped_line)

            y -= line_height

        if line.strip().startswith('-'):
            y -= line_height

        if line.isupper() and len(line) > 3:
            y -= section_spacing

    c.save()

def send_email(pdf_path: str):
   sender = os.getenv("SENDER_EMAIL_ADDRESS")  
   recipient = os.getenv("RECIPIENT_EMAIL_ADDRESS")  

   msg = MIMEMultipart()
   msg['From'] = sender
   msg['To'] = recipient
   msg['Subject'] = f"Gus Logs Daily Report - {datetime.now().strftime('%Y-%m-%d')}"
   
   body = "Please find attached the daily log analysis report."
   msg.attach(MIMEText(body, 'plain'))
   
   with open(pdf_path, 'rb') as f:
       pdf = MIMEApplication(f.read(), _subtype='pdf')
       pdf.add_header('Content-Disposition', 'attachment', filename=os.path.basename(pdf_path))
       msg.attach(pdf)
   
   server = smtplib.SMTP('smtp.gmail.com', 587)
   server.starttls()
   server.login(sender, os.getenv('GMAIL_APP_PASSWORD'))
   server.send_message(msg)
   server.quit()

if __name__ == "__main__":
    filename = f"{datetime.now().strftime('%Y-%m-%d')}_log_summary"
    humanloop_client = Humanloop(
        api_key=os.getenv('HUMANLOOP_API_KEY'),
        base_url=os.getenv("HUMANLOOP_URL")
    )
    file_id = os.getenv('FILE_ID')
    
    logs = get_production_logs(humanloop_client, file_id)
    conversations = group_conversations(logs)
    summaries, errors = batch_analyze(conversations)
    write_summaries_to_file(summaries, errors)
    final_summary = generate_final_summary(f"{filename}.txt", openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY')))
    write_to_pdf(final_summary, f"{filename}.pdf")
    send_email(f"{filename}.pdf")
    print("\nSummaries:", json.dumps(summaries, indent=2))
    print("\nErrors:", errors)
    print("\nFinal Summary:", final_summary)
