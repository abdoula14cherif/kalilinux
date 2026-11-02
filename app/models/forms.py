from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    password = PasswordField("Mot de passe", validators=[DataRequired()])
    submit = SubmitField("Se connecter")

class RegisterForm(FlaskForm):
    full_name = StringField("Nom complet", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    pays_code = SelectField("Pays", validators=[DataRequired()], choices=[
        ("CM", "Cameroun"), ("SN", "Sénégal"), ("CI", "Côte d'Ivoire"),
        ("BJ", "Bénin"), ("TG", "Togo"), ("ML", "Mali"), ("BF", "Burkina Faso"),
        ("NE", "Niger"), ("GN", "Guinée"), ("GA", "Gabon"), ("CG", "Congo"),
    ])
    password = PasswordField("Mot de passe", validators=[
        DataRequired(),
        Length(min=8, message="Le mot de passe doit contenir au moins 8 caractères.")
    ])
    confirm_password = PasswordField("Confirmer le mot de passe", validators=[
        DataRequired(),
        EqualTo("password", message="Les mots de passe ne correspondent pas.")
    ])
    submit = SubmitField("Créer mon compte")