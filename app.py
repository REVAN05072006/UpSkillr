from flask import Flask, render_template, request, redirect, send_from_directory
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
import os
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-default-secret-key")

# Initialize AI client with GitHub token
def get_ai_client():
    try:
        return ChatCompletionsClient(
            endpoint="https://models.github.ai/inference",
            credential=AzureKeyCredential(os.getenv("GITHUB_TOKEN"))
        )
    except Exception as e:
        print(f"Error initializing AI client: {e}")
        return None

def estimate_learning_time(text):
    if not text:
        return "Time estimate unavailable"
    word_count = len(text.split())
    return f"{max(1, round(word_count/100))} minutes"

def generate_content(prompt):
    client = get_ai_client()
    if not client:
        return None, "AI service not available. Please check your token and try again."
    
    try:
        response = client.complete(
            messages=[
                SystemMessage("You are an expert educator creating micro-courses."),
                UserMessage(prompt)
            ],
            temperature=0.7,
            model="deepseek/DeepSeek-V3-0324",
            max_tokens=2000
        )
        return response.choices[0].message.content, None
    except Exception as e:
        return None, f"AI service error: {str(e)}"

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        if not topic:
            return render_template('index.html', error="Topic is required")

        prompt = f"""Create a comprehensive micro-course about {topic} with 3-5 lessons.
        For each lesson, provide:
        1. A clear title (format as "### Lesson [number]: [title]")
        2. 3-5 key learning points (format as bullet points)
        3. A brief summary
        
        Use Markdown formatting for headings and lists.
        Ensure the content is well-structured and easy to follow."""

        content, error = generate_content(prompt)

        if error:
            return render_template('index.html', error=error)

        return render_template('index.html', 
                           topic=topic,
                           content=content,
                           estimated_time=estimate_learning_time(content),
                           show_content=True)

    return render_template('index.html')

@app.route('/quiz', methods=['GET'])
def generate_quiz():
    topic = request.args.get('topic')
    content = request.args.get('content')

    if not topic or not content:
        return redirect('/')

    prompt = f"""Create 5 multiple choice quiz questions about {topic} based on this content:
    {content}

    Format each question exactly like this example:
    Q1. What is the capital of France?
    A) London
    B) Paris
    C) Berlin
    D) Madrid
    Answer: B
    
    Include exactly 4 options (A-D) for each question and clearly mark the correct answer."""

    quiz_content, error = generate_content(prompt)

    if error:
        return render_template('index.html',
                           topic=topic,
                           content=content,
                           error=f"Quiz error: {error}",
                           show_content=True)

    questions = []
    question_blocks = [block.strip() for block in quiz_content.split('\n\n') if block.strip()]
    
    for block in question_blocks[:5]:  # Take max 5 questions
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if len(lines) >= 6 and lines[0].startswith('Q'):
            answer_line = lines[-1]
            correct_answer = re.search(r'Answer:\s*([A-D])', answer_line, re.IGNORECASE)
            if not correct_answer:
                continue
                
            correct_letter = correct_answer.group(1).upper()
            questions.append({
                'text': lines[0][lines[0].find('.')+1:].strip(),
                'options': [opt for opt in lines[1:5] if opt],
                'correct': correct_letter,
                'correct_full': lines[ord(correct_letter) - ord('A') + 1]
            })

    return render_template('index.html',
                       topic=topic,
                       content=content,
                       show_content=True,
                       quiz_data={'questions': questions})

@app.route('/submit-quiz', methods=['POST'])
def submit_quiz():
    topic = request.form.get('topic')
    if not topic:
        return redirect('/')
    
    score = 0
    results = []
    total_questions = 0
    
    for key in request.form:
        if key.startswith('question_'):
            total_questions += 1
    
    for i in range(1, total_questions + 1):
        user_answer = request.form.get(f'q_{i}', '').strip()
        correct_answer = request.form.get(f'correct_full_{i}', '').strip()
        question_text = request.form.get(f'question_{i}', '')
        
        is_correct = user_answer.lower() == correct_answer.lower()
        if is_correct:
            score += 1
            
        results.append({
            'question': question_text,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        })

    percentage = int((score / total_questions) * 100) if total_questions > 0 else 0
    
    if percentage >= 80:
        feedback = "Excellent! You've mastered this topic."
    elif percentage >= 60:
        feedback = "Good job! You have a solid understanding."
    else:
        feedback = "Keep practicing! Review the lessons and try again."

    return render_template('index.html',
                       topic=topic,
                       quiz_result={
                           'score': score,
                           'total': total_questions,
                           'percentage': percentage,
                           'feedback': feedback,
                           'results': results
                       })

if __name__ == '__main__':
    app.run(port=5000, debug=True)