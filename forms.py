from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError, EqualTo
from models import User

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('注册')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('用户名已存在，请选择其他用户名。')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('当前密码', validators=[DataRequired()])
    new_password = PasswordField('新密码', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('确认新密码', validators=[
        DataRequired(), 
        EqualTo('new_password', message='两次输入的密码不一致')
    ])
    submit = SubmitField('修改密码')
    
    def __init__(self, user, *args, **kwargs):
        super(ChangePasswordForm, self).__init__(*args, **kwargs)
        self.user = user
    
    def validate_current_password(self, current_password):
        if not self.user.check_password(current_password.data):
            raise ValidationError('当前密码不正确。')
