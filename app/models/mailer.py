"""
Module Email — Boost Reseller
Utilise Gmail SMTP avec un compte dedie (boostcentralsupport@gmail.com).
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

logger = logging.getLogger(__name__)


def _send(to, subject, html_body):
    """Envoie un email via Gmail SMTP (compte Boost Reseller)."""
    try:
        password = current_app.config.get("GMAIL_APP_PASSWORD", "")
        gmail_user = current_app.config.get("GMAIL_USERNAME", "boostcentralsupport@gmail.com")
        from_name = current_app.config.get("GMAIL_FROM_NAME", "Boost Reseller")

        if not password:
            logger.warning("GMAIL_APP_PASSWORD non configure")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{gmail_user}>"
        msg["To"] = to

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, password)
            server.sendmail(gmail_user, [to], msg.as_string())

        logger.info(f"Email envoye a {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email erreur: {e}")
        return False


def _template(titre, contenu, couleur="#00BFFF", couleur2="#0096C7", emoji="⚡", eyebrow="BOOST RESELLER"):
    """Template HTML commun pour tous les emails."""
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:0;background:#EEF2F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}}
.wrap{{padding:32px 16px}}
.container{{max-width:560px;margin:0 auto;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 10px 40px rgba(15,23,42,.10)}}
.header{{background:linear-gradient(135deg,{couleur},{couleur2});padding:38px 30px 34px;text-align:center;position:relative}}
.header .badge{{display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;background:rgba(255,255,255,.18);border-radius:16px;font-size:1.7rem;margin-bottom:14px}}
.header .eyebrow{{color:rgba(255,255,255,.75);font-size:.72rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin:0 0 6px}}
.header h1{{color:#fff;margin:0;font-size:1.3rem;font-weight:800;line-height:1.35}}
.body{{padding:32px 30px 28px}}
.body p{{color:#475569;line-height:1.7;margin:0 0 14px;font-size:.94rem}}
.box{{background:#F8FAFC;border-radius:14px;padding:18px 20px;margin:18px 0;border:1px solid #E2E8F0}}
.box .row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;font-size:.86rem}}
.box .row+.row{{border-top:1px dashed #E2E8F0}}
.box .row span:first-child{{color:#64748B}}
.box .row span:last-child{{color:#0F172A;font-weight:700;text-align:right}}
.btn-wrap{{text-align:center;margin:24px 0 8px}}
.btn{{display:inline-block;background:linear-gradient(90deg,#00BFFF,#0096C7);color:#fff !important;padding:14px 34px;border-radius:12px;text-decoration:none;font-weight:800;font-size:.92rem;box-shadow:0 8px 20px rgba(0,191,255,.28)}}
.footer{{background:#0F172A;padding:24px 30px;text-align:center;color:rgba(255,255,255,.45);font-size:.76rem;line-height:1.7}}
.footer a{{color:rgba(255,255,255,.75);text-decoration:none;font-weight:600}}
.small-note{{color:#94A3B8;font-size:.8rem;margin-top:22px}}
</style>
</head>
<body>
<div class="wrap">
<div class="container">
<div class="header">
<div class="badge">{emoji}</div>
<p class="eyebrow">{eyebrow}</p>
<h1>{titre}</h1>
</div>
<div class="body">
{contenu}
<p class="small-note">Cet email vous a ete envoye automatiquement. Ne pas repondre.</p>
</div>
<div class="footer">
<p>Boost Reseller • <a href="https://reseller.boostcentral.world">reseller.boostcentral.world</a></p>
<p>Support : <a href="mailto:boostcentralsupport@gmail.com">boostcentralsupport@gmail.com</a></p>
</div>
</div>
</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS REVENDEUR
# ═══════════════════════════════════════════════════════════════

def email_revendeur_nouvelle_commande(to_email, nom_revendeur, nom_boutique,
                                       reference, client_nom, client_telephone,
                                       produits, total, mode_paiement,
                                       lien_commandes):
    """Notifie le revendeur qu'il a recu une nouvelle commande."""
    produits_html = ""
    for p in produits:
        produits_html += f'<div class="row"><span>{p.get("qte", 1)}x {p.get("nom", "")}</span><span>{p.get("prix", 0) * p.get("qte", 1):,.0f} F</span></div>'

    paiement_label = {
        "cash": "Paiement a la livraison",
        "mtn": "MTN Mobile Money",
        "orange": "Orange Money",
    }.get(mode_paiement, mode_paiement)

    contenu = f"""
<p>Bonjour <strong>{nom_revendeur}</strong>,</p>
<p>Vous venez de recevoir une <strong>nouvelle commande</strong> sur votre boutique <strong>{nom_boutique}</strong> !</p>
<div class="box">
<div class="row"><span>Reference</span><span style="font-family:monospace">{reference}</span></div>
<div class="row"><span>Client</span><span>{client_nom}</span></div>
<div class="row"><span>Telephone</span><span>{client_telephone}</span></div>
<div class="row"><span>Paiement</span><span>{paiement_label}</span></div>
</div>
<p><strong>Produits commandes :</strong></p>
<div class="box">
{produits_html}
<div class="row" style="border-top:2px solid #E2E8F0;margin-top:8px;padding-top:8px">
<span><strong>Total</strong></span><span style="color:#059669;font-weight:900;font-size:1.1rem">{total:,.0f} FCFA</span>
</div>
</div>
<div class="btn-wrap"><a href="{lien_commandes}" class="btn">Voir la commande</a></div>
<p style="margin-top:24px;font-size:.82rem;color:#94A3B8">Contactez le client rapidement pour confirmer la commande.</p>
"""
    return _send(
        to_email,
        f"[Commande] {reference} - {total:,.0f} FCFA",
        _template("Nouvelle commande recue !", contenu, "#10B981", "#059669", emoji="🛒")
    )


def email_revendeur_paiement_recu(to_email, nom_revendeur, nom_boutique,
                                   reference, montant, methode, lien_commandes):
    """Notifie le revendeur qu'un paiement a ete recu."""
    methode_label = {
        "cash": "Paiement a la livraison",
        "mtn": "MTN Mobile Money",
        "orange": "Orange Money",
    }.get(methode, methode)

    contenu = f"""
<p>Bonjour <strong>{nom_revendeur}</strong>,</p>
<p>Vous avez recu un paiement sur votre boutique <strong>{nom_boutique}</strong> !</p>
<div class="box">
<div class="row"><span>Reference</span><span style="font-family:monospace">{reference}</span></div>
<div class="row"><span>Montant</span><span style="color:#059669;font-weight:900">{montant:,.0f} FCFA</span></div>
<div class="row"><span>Methode</span><span>{methode_label}</span></div>
</div>
<div class="btn-wrap"><a href="{lien_commandes}" class="btn">Voir la commande</a></div>
"""
    return _send(
        to_email,
        f"[Paiement] {montant:,.0f} FCFA recu",
        _template("Paiement recu !", contenu, "#10B981", "#059669", emoji="💰")
    )


def email_revendeur_nouvel_avis(to_email, nom_revendeur, nom_boutique,
                                  client_nom, note, commentaire, lien_avis):
    """Notifie le revendeur qu'un client a laisse un avis."""
    etoiles = "★" * note + "☆" * (5 - note)
    contenu = f"""
<p>Bonjour <strong>{nom_revendeur}</strong>,</p>
<p>Un client vient de laisser un avis sur votre boutique <strong>{nom_boutique}</strong> !</p>
<div class="box">
<div class="row"><span>Client</span><span>{client_nom}</span></div>
<div class="row"><span>Note</span><span style="color:#F59E0B;font-size:1.1rem">{etoiles} ({note}/5)</span></div>
</div>
{f'<p style="background:#F8FAFC;padding:14px;border-radius:10px;font-style:italic;color:#475569">"{commentaire}"</p>' if commentaire else ''}
<div class="btn-wrap"><a href="{lien_avis}" class="btn">Voir les avis</a></div>
"""
    return _send(
        to_email,
        f"[Avis] {note}/5 de {client_nom}",
        _template("Nouvel avis client !", contenu, "#F59E0B", "#D97706", emoji="⭐")
    )


def email_revendeur_nouveau_client(to_email, nom_revendeur, nom_boutique,
                                     client_email, client_pays, lien_clients):
    """Notifie le revendeur qu'un nouveau client s'est inscrit."""
    contenu = f"""
<p>Bonjour <strong>{nom_revendeur}</strong>,</p>
<p>Un nouveau client s'est inscrit via votre boutique <strong>{nom_boutique}</strong> !</p>
<div class="box">
<div class="row"><span>Email</span><span>{client_email}</span></div>
<div class="row"><span>Pays</span><span>{client_pays or 'Non renseigne'}</span></div>
</div>
<div class="btn-wrap"><a href="{lien_clients}" class="btn">Voir mes clients</a></div>
"""
    return _send(
        to_email,
        f"[Client] {client_email}",
        _template("Nouveau client inscrit !", contenu, "#7C3AED", "#6D28D9", emoji="👤")
    )


def email_revendeur_resume_quotidien(to_email, nom_revendeur, nom_boutique,
                                       nb_commandes, total_ventes, nb_nouveaux_clients,
                                       lien_dashboard):
    """Resume quotidien de l'activite du revendeur."""
    contenu = f"""
<p>Bonjour <strong>{nom_revendeur}</strong>,</p>
<p>Voici votre <strong>resume du jour</strong> pour la boutique <strong>{nom_boutique}</strong> :</p>
<div class="box">
<div class="row"><span>Commandes recues</span><span style="color:#059669;font-weight:900">{nb_commandes}</span></div>
<div class="row"><span>Chiffre d'affaires</span><span style="color:#059669;font-weight:900">{total_ventes:,.0f} FCFA</span></div>
<div class="row"><span>Nouveaux clients</span><span style="color:#0096C7;font-weight:900">{nb_nouveaux_clients}</span></div>
</div>
<div class="btn-wrap"><a href="{lien_dashboard}" class="btn">Voir mon dashboard</a></div>
"""
    return _send(
        to_email,
        f"[Resume] {nb_commandes} commande(s) - {total_ventes:,.0f} FCFA",
        _template("Resume de votre journee", contenu, "#0066FF", "#0047CC", emoji="📊")
    )


def email_revendeur_stock_bas(to_email, nom_revendeur, nom_boutique,
                                produit_nom, stock_restant, lien_produits):
    """Alerte le revendeur qu'un produit est presque en rupture."""
    contenu = f"""
<p>Bonjour <strong>{nom_revendeur}</strong>,</p>
<p>Un produit de votre boutique <strong>{nom_boutique}</strong> est presque en rupture de stock.</p>
<div class="box">
<div class="row"><span>Produit</span><span>{produit_nom}</span></div>
<div class="row"><span>Stock restant</span><span style="color:#DC2626;font-weight:900">{stock_restant} unite(s)</span></div>
</div>
<div class="btn-wrap"><a href="{lien_produits}" class="btn">Gerer mon stock</a></div>
"""
    return _send(
        to_email,
        f"[Stock] {produit_nom} - {stock_restant} unite(s)",
        _template("Stock bas !", contenu, "#DC2626", "#991B1B", emoji="🚨")
    )


# ═══════════════════════════════════════════════════════════════
# EMAIL CLIENT — CONFIRMATION DE COMMANDE
# ═══════════════════════════════════════════════════════════════

def email_client_confirmation_commande(to_email, nom_client, nom_boutique,
                                         reference, produits, total,
                                         lien_confirmation, whatsapp_vendeur):
    """Email de confirmation envoye au client qui vient de commander."""
    produits_html = ""
    for p in produits:
        produits_html += f'<div class="row"><span>{p.get("qte", 1)}x {p.get("nom", "")}</span><span>{p.get("prix", 0) * p.get("qte", 1):,.0f} F</span></div>'

    contenu = f"""
<p>Bonjour <strong>{nom_client}</strong>,</p>
<p>Merci pour votre commande sur <strong>{nom_boutique}</strong> !</p>
<p>Votre commande a bien ete enregistree. Le vendeur va vous contacter rapidement pour la livraison.</p>

<div class="box">
<div class="row"><span>Reference</span><span style="font-family:monospace">{reference}</span></div>
</div>

<p><strong>Vos produits :</strong></p>
<div class="box">
{produits_html}
<div class="row" style="border-top:2px solid #E2E8F0;margin-top:8px;padding-top:8px">
<span><strong>Total</strong></span><span style="color:#059669;font-weight:900;font-size:1.1rem">{total:,.0f} FCFA</span>
</div>
</div>

<div class="btn-wrap"><a href="{lien_confirmation}" class="btn">Voir ma commande</a></div>

<p style="margin-top:24px;font-size:.82rem;color:#94A3B8">Une question ? Contactez le vendeur sur WhatsApp.</p>
"""
    return _send(
        to_email,
        f"[Commande] {reference} confirmee",
        _template("Commande confirmee !", contenu, "#10B981", "#059669", emoji="✅")
    )