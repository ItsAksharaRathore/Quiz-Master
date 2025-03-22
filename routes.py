from flask import render_template, redirect, url_for, flash, request, session, json
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from sqlalchemy import func, or_
from werkzeug.security import generate_password_hash, check_password_hash
import os
import io
import base64
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import seaborn as sns
import plotly.graph_objs as go
import plotly.io as pio
import re

from app import app, db
from models import User, Subject, Chapter, Quiz, Question, Score, QuizAttempt, QuizAnswer

def save_quiz_attempt(user_id, quiz_id, score, total_questions):
    """
    Create a new quiz attempt record.
    
    Args:
        user_id: ID of the user taking the quiz
        quiz_id: ID of the quiz being taken
        score: Score achieved in the quiz
        total_questions: Total number of questions in the quiz
    
    Returns:
        The created QuizAttempt object
    """
    # Create new attempt record
    attempt = QuizAttempt(
        user_id=user_id,
        quiz_id=quiz_id,
        score=score,
        total_questions=total_questions,
        timestamp=datetime.now()  # This captures the exact time the quiz was completed
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    return redirect(url_for('index'))

@app.route('/index')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    return render_template('index.html')

def is_valid_gmail(email):
    """Check if the email follows @gmail.com format"""
    return re.fullmatch(r'^[a-zA-Z0-9._%+-]+@gmail\.com$', email) is not None

@app.route('/login', methods=['GET', 'POST'])

def login():
    # If user is already logged in, redirect them
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if all fields are filled
        if not username or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for('login'))
         # Validate email format
        if not is_valid_gmail(username):
            flash("Invalid email! Please use a @gmail.com email address.", "danger")
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()

        # Special handling for admin
        if user and user.is_admin and user.check_password(password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))

        if user and user.check_password(password):
            if user.approval_status == 'pending':
                flash('Your account is pending admin approval.', 'warning')
                return redirect(url_for('login'))
            elif user.approval_status == 'rejected':
                flash('Your account has been rejected. Please contact administrator.', 'danger')
                return redirect(url_for('login'))

            login_user(user)
            return redirect(url_for('user_dashboard'))

        flash('Invalid username or password', 'danger')

    return render_template('login.html')



@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        qualification = request.form.get('qualification')
        dob = request.form.get('dob')

        # Check if all fields are filled
        if not all([username, password, full_name, qualification, dob]):
            flash("All fields are required!", "danger")
            return redirect(url_for('register'))
        # Validate email format
        if not is_valid_gmail(username):
            flash("Invalid email! Please use a @gmail.com email address.", "danger")
            return redirect(url_for('register'))

        try:
            user = User(
                username=username,
                full_name=full_name,
                qualification=qualification,
                dob=datetime.strptime(dob, '%Y-%m-%d'),
                approval_status='pending'  # Default status
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash('Registration successful! Your account is pending admin approval.', 'info')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'danger')

    return render_template('register.html')



@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('user_dashboard'))
    
    # Show all subjects
    subjects = Subject.query.all()
    
    # Show users by approval status
    pending_users = User.query.filter_by(is_admin=False, approval_status='pending').all()
    rejected_users = User.query.filter_by(is_admin=False, approval_status='rejected').all()
    approved_users = User.query.filter_by(is_admin=False, approval_status='approved').all()
    
    return render_template('admin/dashboard.html', 
                           subjects=subjects, 
                           pending_users=pending_users,
                           rejected_users=rejected_users,
                           approved_users=approved_users)

@app.route('/admin/charts')
@login_required
def admin_charts():
    """Route for Admin Dashboard Charts"""
    if not current_user.is_admin:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('home'))

    # Fetch all subjects
    subjects = Subject.query.all()

    # 📌 Get Top Scores and Attempts Per Subject
    subject_names, top_scores, attempts = [], [], []

    for subject in subjects:
        highest_score = db.session.query(func.max(QuizAttempt.score)).join(Quiz).join(Chapter).filter(Chapter.subject_id == subject.id).scalar() or 0
        attempt_count = QuizAttempt.query.join(Quiz).join(Chapter).filter(Chapter.subject_id == subject.id).count()

        subject_names.append(subject.name)
        top_scores.append(highest_score)
        attempts.append(attempt_count)

    # Convert data to DataFrame
    df = pd.DataFrame({'Subject': subject_names, 'Top Score': top_scores, 'Attempts': attempts})

    # 📊 **Bar Chart: Subject-wise Top Scores**
    plt.figure(figsize=(8, 5))
    c = ['#DE3163','#6495ED','#CCCCFF','#DFFF00','#FFBF00']
    plt.bar(df['Subject'], df['Top Score'], color=c)
    plt.xlabel('Subjects')
    plt.ylabel('Top Score')
    plt.title('Top Scores Per Subject')
    plt.xticks(rotation=45)
    plt.savefig(os.path.join('static', 'subject_top_scores.png'))
    plt.close()

    # 📈 **Line Chart: Subject-wise Quiz Attempts**
    plt.figure(figsize=(8, 5))
    
    plt.plot(df['Subject'], df['Attempts'], marker='o', linestyle='-', color='#00FF00')
    plt.xlabel('Subjects')
    plt.ylabel('Attempts')
    plt.title('Quiz Attempts Per Subject')
    plt.xticks(rotation=45)
    plt.savefig(os.path.join('static', 'subject_attempts.png'))
    plt.close()

    # 🥧 **Pie Chart: Attempt Distribution**
    plt.figure(figsize=(6, 6))
    plt.pie(df['Attempts'], labels=df['Subject'], autopct='%1.1f%%', colors=plt.cm.Paired.colors, startangle=140)
    plt.title("Quiz Attempt Distribution")
    plt.savefig(os.path.join('static', 'quiz_pie_chart.png'))
    plt.close()

        # 📌 **User Approval Status Chart**
    approval_labels = ["Approved", "Pending", "Rejected"]
    approval_counts = [
        User.query.filter_by(approval_status='approved').count(),
        User.query.filter_by(approval_status='pending').count()-1,  # No need to subtract
        User.query.filter_by(approval_status='rejected').count()
    ]

    plt.figure(figsize=(7, 5))
    plt.bar(approval_labels, approval_counts, color=['#28a745', '#ffc107', '#dc3545'])
    plt.xlabel("Approval Status")
    plt.ylabel("Number of Users")
    plt.title("User Approval Status")
    plt.savefig(os.path.join('static', 'user_approval_chart.png'))
    plt.close()

    # 📊 **Interactive Plotly Chart**
    fig = px.bar(df, x='Subject', y=['Top Score', 'Attempts'],
                 title="Admin Quiz Insights",
                 barmode='group', text_auto=True)
    plot_html = fig.to_html(full_html=False)

    return render_template('admin/admin_charts.html', plot_html=plot_html)


@app.route('/admin/user_management')
@login_required
def user_management():
    if not current_user.is_admin:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('home'))

    pending_users = User.query.filter_by(approval_status='pending', is_admin=False).all()
    approved_users = User.query.filter_by(approval_status='approved', is_admin=False).all()
    rejected_users = User.query.filter_by(approval_status='rejected', is_admin=False).all()

    return render_template('admin/user_management.html', 
                           pending_users=pending_users, 
                           approved_users=approved_users, 
                           rejected_users=rejected_users)


@app.route('/admin/users')
@login_required
def user_list():
    if not current_user.is_admin:
        return redirect(url_for('home'))
    
    users = User.query.filter_by(is_admin=False).all()
    
    # Fetch quiz attempts for each user
    user_attempts = {user.id: QuizAttempt.query.filter_by(user_id=user.id).order_by(QuizAttempt.timestamp.desc()).all() for user in users}

    return render_template('admin/user_list.html', users=users, user_attempts=user_attempts)


@app.route('/admin/user/<int:user_id>')
@login_required
def user_details(user_id):
    if not current_user.is_admin:
        return redirect(url_for('home'))
    user = User.query.get_or_404(user_id)
    attempts = QuizAttempt.query.filter_by(user_id=user.id).order_by(QuizAttempt.timestamp.desc()).all()
    return render_template('admin/user_details.html', user=user, attempts=attempts)


@app.route('/admin/user/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    user.approval_status = 'approved'
    db.session.commit()
    flash(f'User {user.username} has been approved.', 'success')
    
    # Redirect to the correct user management page
    return redirect(url_for('user_management'))

@app.route('/admin/user/reject/<int:user_id>', methods=['POST'])
@login_required
def reject_user(user_id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    user.approval_status = 'rejected'
    db.session.commit()
    flash(f'User {user.username} has been rejected.', 'success')

    # Redirect to the correct user management page
    return redirect(url_for('user_management'))



@app.route('/user')
@login_required
def user_dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
        
    # Get quiz attempts with time_taken information
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id)\
        .order_by(QuizAttempt.timestamp.desc()).all()
    
    # Get all available subjects with their chapters and quizzes
    subjects = Subject.query.all()
    
    # Get recent scores for the chart (limited to last 10)
    scores = QuizAttempt.query.filter_by(user_id=current_user.id)\
        .order_by(QuizAttempt.timestamp.desc()).limit(10).all()
    
    return render_template('user/dashboard.html', 
                         attempts=attempts,
                         subjects=subjects,
                         scores=scores)



# Subject Operations
@app.route('/admin/subject/new', methods=['GET', 'POST'])
@login_required
def new_subject():
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Subject name is required', 'danger')
                return redirect(url_for('new_subject'))

            # Check for duplicate subject name
            existing_subject = Subject.query.filter(func.lower(Subject.name) == func.lower(name)).first()
            if existing_subject:
                flash('A subject with this name already exists', 'danger')
                return redirect(url_for('new_subject'))

            subject = Subject(name=name, description=description)
            db.session.add(subject)
            db.session.commit()
            flash('Subject created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating subject: {str(e)}', 'danger')
            return redirect(url_for('new_subject'))
            
    return render_template('admin/create_subject.html')

@app.route('/admin/subject/edit/<int:subject_id>', methods=['GET', 'POST'])
@login_required
def edit_subject(subject_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))
    
    subject = Subject.query.get_or_404(subject_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Subject name is required', 'danger')
                return redirect(url_for('edit_subject', subject_id=subject_id))

            # Check for duplicate name, excluding current subject
            existing_subject = Subject.query.filter(
                func.lower(Subject.name) == func.lower(name),
                Subject.id != subject_id
            ).first()
            if existing_subject:
                flash('A subject with this name already exists', 'danger')
                return redirect(url_for('edit_subject', subject_id=subject_id))

            subject.name = name
            subject.description = description
            db.session.commit()
            flash('Subject updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating subject: {str(e)}', 'danger')
            return redirect(url_for('edit_subject', subject_id=subject_id))
    
    return render_template('admin/edit_subject.html', subject=subject)
@app.route('/admin/subject/delete/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))

    try:
        subject = Subject.query.get_or_404(subject_id)

        # Delete quiz answers first
        quiz_answers = QuizAnswer.query.join(QuizAttempt).join(Quiz).join(Chapter).filter(Chapter.subject_id == subject_id).all()
        for answer in quiz_answers:
            db.session.delete(answer)

        db.session.commit()  # Commit before deleting attempts

        # Delete quiz attempts
        quiz_attempts = QuizAttempt.query.join(Quiz).join(Chapter).filter(Chapter.subject_id == subject_id).all()
        for attempt in quiz_attempts:
            db.session.delete(attempt)

        db.session.commit()  # Commit before deleting quizzes

        # Now delete the subject (quizzes & attempts will be deleted via cascade)
        db.session.delete(subject)
        db.session.commit()
        
        flash('Subject and all related data deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting subject: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))


# Chapter Operations
@app.route('/admin/chapter/new/<int:subject_id>', methods=['GET', 'POST'])
@login_required
def new_chapter(subject_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))
    
    subject = Subject.query.get_or_404(subject_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Chapter name is required', 'danger')
                return redirect(url_for('new_chapter', subject_id=subject_id))

            # Check for duplicate chapter name within the subject
            existing_chapter = Chapter.query.filter(
                func.lower(Chapter.name) == func.lower(name),
                Chapter.subject_id == subject_id
            ).first()
            if existing_chapter:
                flash('A chapter with this name already exists in this subject', 'danger')
                return redirect(url_for('new_chapter', subject_id=subject_id))

            chapter = Chapter(
                name=name,
                description=description,
                subject_id=subject_id
            )
            db.session.add(chapter)
            db.session.commit()
            flash('Chapter created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating chapter: {str(e)}', 'danger')
            return redirect(url_for('new_chapter', subject_id=subject_id))
    
    return render_template('admin/create_chapter.html', subject_id=subject_id, subject=subject)

@app.route('/admin/chapter/edit/<int:chapter_id>', methods=['GET', 'POST'])
@login_required
def edit_chapter(chapter_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))
    
    chapter = Chapter.query.get_or_404(chapter_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Chapter name is required', 'danger')
                return redirect(url_for('edit_chapter', chapter_id=chapter_id))

            # Check for duplicate name within the same subject
            existing_chapter = Chapter.query.filter(
                func.lower(Chapter.name) == func.lower(name),
                Chapter.subject_id == chapter.subject_id,
                Chapter.id != chapter_id
            ).first()
            if existing_chapter:
                flash('A chapter with this name already exists in this subject', 'danger')
                return redirect(url_for('edit_chapter', chapter_id=chapter_id))

            chapter.name = name
            chapter.description = description
            db.session.commit()
            flash('Chapter updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating chapter: {str(e)}', 'danger')
            return redirect(url_for('edit_chapter', chapter_id=chapter_id))
    
    return render_template('admin/edit_chapter.html', chapter=chapter)

@app.route('/admin/chapter/delete/<int:chapter_id>', methods=['POST'])
@login_required
def delete_chapter(chapter_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))

    try:
        chapter = Chapter.query.get_or_404(chapter_id)
        db.session.delete(chapter)
        db.session.commit()
        flash('Chapter and all related quizzes deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting chapter: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))


# Quiz Operations
@app.route('/admin/quiz/new/<int:chapter_id>', methods=['GET', 'POST'])
@login_required
def new_quiz(chapter_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))

    chapter = Chapter.query.get_or_404(chapter_id)

    if request.method == 'POST':
        try:
            # Validate basic quiz information
            start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
            time_duration = int(request.form['time_duration'])
            
            if start_time < datetime.now():
                flash('Start time cannot be in the past', 'danger')
                return redirect(url_for('new_quiz', chapter_id=chapter_id))
                
            if end_time <= start_time:
                flash('End time must be after start time', 'danger')
                return redirect(url_for('new_quiz', chapter_id=chapter_id))
                
            if time_duration < 2 or time_duration > 120:
                flash('Quiz duration must be between 2 and 120 minutes', 'danger')
                return redirect(url_for('new_quiz', chapter_id=chapter_id))

            # Create quiz
            quiz = Quiz(
                chapter_id=chapter_id,
                start_time=start_time,
                end_time=end_time,
                time_duration=time_duration,
                remarks=request.form.get('remarks', '').strip()
            )
            db.session.add(quiz)
            db.session.flush()

            # Validate and add questions
            num_questions = int(request.form.get('num_questions', 0))
            if num_questions < 1 or num_questions > 20:
                flash('Number of questions must be between 1 and 20', 'danger')
                return redirect(url_for('new_quiz', chapter_id=chapter_id))

            for i in range(1, num_questions + 1):
                question_text = request.form.get(f'question_{i}', '').strip()
                if not question_text:
                    flash(f'Question {i} statement is required', 'danger')
                    return redirect(url_for('new_quiz', chapter_id=chapter_id))

                # Validate options
                options = [
                    request.form.get(f'option1_{i}', '').strip(),
                    request.form.get(f'option2_{i}', '').strip(),
                    request.form.get(f'option3_{i}', '').strip(),
                    request.form.get(f'option4_{i}', '').strip()
                ]
                
                if any(not option for option in options):
                    flash(f'All options for question {i} are required', 'danger')
                    return redirect(url_for('new_quiz', chapter_id=chapter_id))

                correct_option = int(request.form.get(f'correct_option_{i}', 0))
                if correct_option < 1 or correct_option > 4:
                    flash(f'Invalid correct option for question {i}', 'danger')
                    return redirect(url_for('new_quiz', chapter_id=chapter_id))

                question = Question(
                    quiz_id=quiz.id,
                    question_statement=question_text,
                    option1=options[0],
                    option2=options[1],
                    option3=options[2],
                    option4=options[3],
                    correct_option=correct_option
                )
                db.session.add(question)

            db.session.commit()
            flash('Quiz created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        except ValueError as e:
            db.session.rollback()
            flash('Invalid date/time format', 'danger')
            return redirect(url_for('new_quiz', chapter_id=chapter_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating quiz: {str(e)}', 'danger')
            return redirect(url_for('new_quiz', chapter_id=chapter_id))

    return render_template('admin/create_quiz.html', chapter=chapter)

@app.route('/admin/quiz/edit/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
def edit_quiz(quiz_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))

    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if quiz has any attempts
    if QuizAttempt.query.filter_by(quiz_id=quiz_id).first():
        flash('Cannot edit quiz that has been attempted by users', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        try:
            # Validate dates and duration
            start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
            time_duration = int(request.form['time_duration'])
            
            if start_time < datetime.now():
                flash('Start time cannot be in the past', 'danger')
                return redirect(url_for('edit_quiz', quiz_id=quiz_id))
                
            if end_time <= start_time:
                flash('End time must be after start time', 'danger')
                return redirect(url_for('edit_quiz', quiz_id=quiz_id))
                
            if time_duration < 2 or time_duration > 120:
                flash('Quiz duration must be between 2 and 120 minutes', 'danger')
                return redirect(url_for('edit_quiz', quiz_id=quiz_id))

            # Update quiz details
            quiz.start_time = start_time
            quiz.end_time = end_time
            quiz.time_duration = time_duration
            quiz.remarks = request.form.get('remarks', '').strip()

            # Update existing questions
            for question in quiz.questions:
                question_id = str(question.id)
                
                question_text = request.form.get(f'question_{question_id}', '').strip()
                if not question_text:
                    flash(f'Question statement is required', 'danger')
                    return redirect(url_for('edit_quiz', quiz_id=quiz_id))

                options = [
                    request.form.get(f'option1_{question_id}', '').strip(),
                    request.form.get(f'option2_{question_id}', '').strip(),
                    request.form.get(f'option3_{question_id}', '').strip(),
                    request.form.get(f'option4_{question_id}', '').strip()
                ]
                
                if any(not option for option in options):
                    flash('All options are required for each question', 'danger')
                    return redirect(url_for('edit_quiz', quiz_id=quiz_id))

                correct_option = int(request.form.get(f'correct_option_{question_id}', 0))
                if correct_option < 1 or correct_option > 4:
                    flash('Invalid correct option', 'danger')
                    return redirect(url_for('edit_quiz', quiz_id=quiz_id))

                # Update question
                question.question_statement = question_text
                question.option1 = options[0]
                question.option2 = options[1]
                question.option3 = options[2]
                question.option4 = options[3]
                question.correct_option = correct_option

            db.session.commit()
            flash('Quiz updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        except ValueError as e:
            db.session.rollback()
            flash('Invalid date/time format', 'danger')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating quiz: {str(e)}', 'danger')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))

    return render_template('admin/edit_quiz.html', quiz=quiz)

@app.route('/admin/quiz/delete/<int:quiz_id>', methods=['POST'])
@login_required
def delete_quiz(quiz_id):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('home'))

    try:
        quiz = Quiz.query.get_or_404(quiz_id)

        # Check if quiz has been attempted
        if QuizAttempt.query.filter_by(quiz_id=quiz_id).first():
            flash('Cannot delete quiz that has been attempted by users', 'danger')
            return redirect(url_for('admin_dashboard'))

        db.session.delete(quiz)
        db.session.commit()
        flash('Quiz and all related questions deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting quiz: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))



@app.route('/quiz/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    # Check if the user is approved
    if not is_approved():
        flash("You are not approved to take this quiz.", "danger")
        return redirect(url_for('home'))

    # Check if the user has already attempted the quiz
    existing_attempt = QuizAttempt.query.filter_by(quiz_id=quiz_id, user_id=current_user.id).first()
    if existing_attempt:
        flash("You have already attempted this quiz.", "info")
        return redirect(url_for('view_result', attempt_id=existing_attempt.id))

    quiz_data = {
        'id': quiz.id,
        'duration': quiz.time_duration,
        'start_time': quiz.start_time.strftime('%Y-%m-%d %H:%M:%S'),  # Convert datetime to string
        'end_time': quiz.end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'questions': [
            {
                'id': question.id,
                'statement': question.question_statement,
                'option1': question.option1,
                'option2': question.option2,
                'option3': question.option3,
                'option4': question.option4
            } for question in quiz.questions
        ]
    }

    return render_template('quiz/take_quiz.html', quiz_data=quiz_data)

def is_approved():
    return current_user.approval_status if hasattr(current_user, 'approval_status') else False



@app.route('/quiz/<int:quiz_id>/submit', methods=['POST'])
@login_required
def submit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    score = 0
    total_questions = len(quiz.questions)
    
    # Create new quiz attempt
    attempt = QuizAttempt(
        quiz_id=quiz_id,
        user_id=current_user.id,
        score=0,
        total_questions=total_questions
    )
    db.session.add(attempt)
    db.session.flush()  # Get attempt ID
    
    # Process each question and store answers
    for question in quiz.questions:
        try:
            selected_option = int(request.form.get(f'q{question.id}', '0').strip())
        except ValueError:
            selected_option = 0
            
        is_correct = (selected_option == question.correct_option)
        if is_correct:
            score += 1
            
        # Store detailed answer
        answer = QuizAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_option=selected_option,
            is_correct=is_correct
        )
        db.session.add(answer)
    
    # Update attempt score
    attempt.score = score
    
    # Handle the Score table entry
    existing_score = Score.query.filter_by(quiz_id=quiz_id, user_id=current_user.id).first()
    
    if existing_score:
        # Update existing score
        existing_score.total_scored = score
        existing_score.total_questions = total_questions
        existing_score.timestamp = datetime.utcnow()
    else:
        # Create new score entry
        new_score = Score(
            quiz_id=quiz_id,
            user_id=current_user.id,
            total_scored=score,
            total_questions=total_questions
        )
        db.session.add(new_score)

    db.session.commit()
    
    flash(f'Quiz submitted! Your score: {score}/{total_questions}', 'success')
    # Redirect to the detailed results view
    return redirect(url_for('view_result', attempt_id=attempt.id))



@app.route('/result/<int:attempt_id>')
@login_required
def view_result(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)

    # Ensure user can only view their own results
    if attempt.user_id != current_user.id and not current_user.is_admin:
        flash('You do not have permission to view this result.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    return render_template('quiz/result.html', attempt=attempt)




@app.route('/quiz/result')
@login_required
def view_results():
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id).order_by(QuizAttempt.timestamp.desc()).all()
    return render_template('quiz/result.html', attempts=attempts)



@app.route('/charts')
@login_required
def view_charts():
    """Route to display comprehensive quiz charts"""
    quiz_attempts = QuizAttempt.query.filter_by(user_id=current_user.id).all()

    # Prepare data for visualization
    chart_data = []
    for attempt in quiz_attempts:
        chart_data.append({
            'Subject': attempt.quiz.chapter.subject.name,
            'Score': attempt.score,
            'Total Questions': attempt.total_questions,
            'Timestamp': attempt.timestamp
        })

    if not chart_data:
        chart_data = [{'Subject': 'No Data', 'Score': 0, 'Total Questions': 0, 'Timestamp': None}]

    df = pd.DataFrame(chart_data)

    # Convert Timestamp to datetime
    if 'Timestamp' in df and not df['Timestamp'].isna().all():
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df = df.sort_values(by='Timestamp')

    img_data = {}

    # Function to save plots in memory
    def get_plot():
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight')
        plt.close()
        img.seek(0)
        return base64.b64encode(img.getvalue()).decode('utf8')

    # 1️⃣ **Bar Chart: Average Score per Subject**
    c2 = ['#CCCCFF','#DFFF00','#DE3163','#6495ED','#FFBF00']
    plt.figure(figsize=(10, 6))
    subject_avg_scores = df.groupby('Subject')['Score'].mean()

    if subject_avg_scores.empty:
        subject_avg_scores = pd.Series([0], index=['No Data'])

    subject_avg_scores.plot(kind='bar', color=c2, edgecolor='black')
    plt.title('Average Quiz Scores by Subject', fontsize=15)
    plt.xlabel('Subject', fontsize=12)
    plt.ylabel('Average Score', fontsize=12)
    plt.xticks(rotation=45)
    img_data['bar_chart'] = get_plot()

    # 2️⃣ **Line Chart: Score Progression Over Time (Matplotlib)**
    if 'Timestamp' in df and not df['Timestamp'].isna().all():
        df = df.sort_values(by='Timestamp')  # Ensure data is sorted by date
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

        plt.figure(figsize=(12, 6))
        plt.plot(df['Timestamp'], df['Score'], marker='*', linestyle='-', color='#800080', label="Score Progression")

        plt.title('Quiz Score Progression Over Time', fontsize=15)
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Score', fontsize=12)
        plt.xticks(rotation=45)
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.6)

        img_data['line_chart'] = get_plot()



    # 3️⃣ **Pie Chart: Quiz Distribution by Subject**
    subject_quiz_count = df['Subject'].value_counts()
    if subject_quiz_count.empty:
        subject_quiz_count = pd.Series([1], index=['No Data'])

    plt.figure(figsize=(8, 8))
    plt.pie(subject_quiz_count, labels=subject_quiz_count.index, autopct='%1.1f%%',
            startangle=140, wedgeprops={'edgecolor': 'black'},colors=c2)
    plt.title('Quiz Distribution by Subject', fontsize=15)
    img_data['pie_chart'] = get_plot()

    # 4️⃣ **Scatter Plot: Score vs Total Questions**
    plt.figure(figsize=(10, 6))
    plt.scatter(df['Total Questions'], df['Score'], alpha=0.7, c=df['Score'], cmap='viridis', edgecolors='black')
    plt.colorbar(label='Score')
    plt.title('Score Distribution by Total Questions', fontsize=15)
    plt.xlabel('Total Questions', fontsize=12)
    plt.ylabel('Score', fontsize=12)
    img_data['scatter_chart'] = get_plot()

    # 5️⃣ **Interactive Plotly Chart**
    fig = go.Figure()

    # Bar trace for average scores
    fig.add_trace(go.Bar(
        x=subject_avg_scores.index,
        y=subject_avg_scores.values,
        name='Average Score',
        marker_color='rgba(60, 61, 70, 0.55)'
    ))

    # Line trace for score progression
    if 'Timestamp' in df and not df['Timestamp'].isna().all():
        fig.add_trace(go.Scatter(
            x=df['Timestamp'],
            y=df['Score'],
            mode='lines+markers',
            name='Score Progression',
            line=dict(color='green', width=2)
        ))

    fig.update_layout(
        title='Interactive Quiz Performance Overview',
        xaxis_title='Subject/Date',
        yaxis_title='Score',
        barmode='overlay'
    )

    plot_html = fig.to_html(full_html=False)

    return render_template(
        'quiz/charts.html',
        plot_html=plot_html,
        img_data=img_data
    )


@app.route('/search', methods=['GET'])
@login_required
def search():
    # Check if the user is an admin, if not redirect to home page
    if not current_user.is_admin:
        flash('Only administrators can access search functionality', 'danger')
        return redirect(url_for('home'))
        
    query = request.args.get('query', '').strip()
    
    if not query:
        flash('Please enter a search term', 'warning')
        return redirect(url_for('home'))
    
    # Search results storage
    search_results = {}
    
    # Search Users
    users = User.query.filter(
        db.and_(User.is_admin == 0,
            db.or_(
            User.username.ilike(f'%{query}%'),
            User.full_name.ilike(f'%{query}%'),
            User.qualification.ilike(f'%{query}%')
        )
        )
        
    ).all()
    if users:
        search_results['users'] = users
    
    # Search Subjects
    subjects = Subject.query.filter(
        db.or_(
            Subject.name.ilike(f'%{query}%'),
            Subject.description.ilike(f'%{query}%')
        )
    ).all()
    if subjects:
        search_results['subjects'] = subjects
    
    # Search Chapters
    chapters = Chapter.query.filter(
        db.or_(
            Chapter.name.ilike(f'%{query}%'),
            Chapter.description.ilike(f'%{query}%')
        )
    ).all()
    if chapters:
        search_results['chapters'] = chapters
    
    # Search Quizzes
    quizzes = Quiz.query.join(Chapter).filter(
        db.or_(
            Chapter.name.ilike(f'%{query}%'),
            Quiz.remarks.ilike(f'%{query}%')
        )
    ).all()
    if quizzes:
        search_results['quizzes'] = quizzes
    
    # Search Questions - only return MCQs with one correct option
    questions = Question.query.filter(
        db.or_(
            Question.question_statement.ilike(f'%{query}%'),
            Question.option1.ilike(f'%{query}%'),
            Question.option2.ilike(f'%{query}%'),
            Question.option3.ilike(f'%{query}%'),
            Question.option4.ilike(f'%{query}%')
        )
    ).all()
    if questions:
        search_results['questions'] = questions
    
    # If no results found
    if not search_results:
        flash(f'No results found for "{query}"', 'info')
        return redirect(url_for('home'))
    
    return render_template('search_results.html', 
                           results=search_results, 
                           query=query)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('role', None)  # Remove role from session
    return redirect(url_for('home'))