"""
Module Email — Boost Reseller
Utilise Gmail SMTP avec un compte dedie.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

logger = logging.getLogger(__name__)


def _send(to, subject, html_body):
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

        logger.info(f"Email envoye a {to}")
        return True
    except Exception as e:
        logger.error(f"Email erreur: {type(e).__name__}")
        return False


def _template(titre, contenu, couleur="#00BFFF", couleur2="#0096C7", emoji="⚡", eyebrow="BOOST RESELLER"):
    """Template HTML premium pour tous les emails."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titre}</title>
</head>
<body style="margin:0;padding:0;background:#EEF2F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased">

<!-- Wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#EEF2F9;padding:40px 16px">
<tr>
<td align="center">

<!-- Container -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 20px 60px rgba(15,23,42,.10),0 4px 12px rgba(15,23,42,.06)">

<!-- Header avec dégradé -->
<tr>
<td style="background:linear-gradient(135deg,{couleur} 0%,{couleur2} 100%);padding:44px 40px 40px;text-align:center;position:relative">
  <div style="display:inline-block;width:72px;height:72px;background:rgba(255,255,255,.20);border-radius:20px;line-height:72px;font-size:32px;margin-bottom:18px;backdrop-filter:blur(10px)">{emoji}</div>
  <div style="color:rgba(255,255,255,.75);font-size:11px;font-weight:800;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px">{eyebrow}</div>
  <h1 style="color:#ffffff;margin:0;font-size:24px;font-weight:800;line-height:1.3;letter-spacing:-0.3px">{titre}</h1>
</td>
</tr>

<!-- Body -->
<tr>
<td style="padding:38px 40px 32px">
{contenu}
<p style="color:#94A3B8;font-size:12px;line-height:1.6;margin:28px 0 0;padding-top:24px;border-top:1px dashed #E2E8F0">
  Cet email vous a été envoyé automatiquement par Boost Reseller. Merci de ne pas y répondre directement.
</p>
</td>
</tr>

<!-- Footer -->
<tr>
<td style="background:#0F172A;padding:28px 40px;text-align:center">
  <div style="color:#ffffff;font-size:14px;font-weight:800;letter-spacing:.5px;margin-bottom:8px">BOOST RESELLER</div>
  <div style="color:rgba(255,255,255,.5);font-size:12px;line-height:1.7">
    <a href="https://reseller.boostcentral.world" style="color:rgba(255,255,255,.75);text-decoration:none;font-weight:600">reseller.boostcentral.world</a>
  </div>
  <div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,.1);color:rgba(255,255,255,.4);font-size:11px">
    Support : <a href="mailto:boostcentralsupport@gmail.com" style="color:#00BFFF;text-decoration:none;font-weight:600">boostcentralsupport@gmail.com</a>
  </div>
</td>
</tr>

</table>

<!-- Footer externe -->
<div style="text-align:center;padding:24px 16px 0;color:#94A3B8;font-size:11px;line-height:1.6">
  © 2026 Boost Reseller — Propulsé par Boost Central
</div>

</td>
</tr>
</table>

</body>
</html>"""


def _box(rows):
    """Génère un encadré avec des lignes clé/valeur."""
    rows_html = ""
    for i, (label, value) in enumerate(rows):
        border = "border-top:1px dashed #E2E8F0;" if i > 0 else ""
        rows_html += f"""<tr>
<td style="padding:10px 0;{border}color:#64748B;font-size:13px;font-weight:600;vertical-align:top">{label}</td>
<td style="padding:10px 0;{border}color:#0F172A;font-size:14px;font-weight:700;text-align:right;vertical-align:top">{value}</td>
</tr>"""
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F8FAFC;border-radius:14px;padding:0;margin:20px 0;border:1px solid #E2E8F0">
<tr>
<td style="padding:18px 22px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{rows_html}
</table>
</td>
</tr>
</table>"""


def _btn(text, url, couleur="#00BFFF", couleur2="#0096C7"):
    """Génère un bouton CTA."""
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:26px auto 8px">
<tr>
<td align="center" style="border-radius:14px;background:linear-gradient(135deg,{couleur},{couleur2});box-shadow:0 10px 24px rgba(0,191,255,.30)">
<a href="{url}" target="_blank" style="display:inline-block;padding:16px 40px;color:#ffffff;text-decoration:none;font-weight:800;font-size:15px;border-radius:14px;letter-spacing:.2px">{text}</a>
</td>
</tr>
</table>"""


def _produits_table(produits):
    """Génère un tableau de produits."""
    rows = ""
    for p in produits:
        qte = p.get("qte", 1)
        nom = p.get("nom", "")
        prix = p.get("prix", 0) * qte
        rows += f"""<tr>
<td style="padding:12px 0;border-bottom:1px solid #F1F5F9;vertical-align:middle">
  <div style="color:#0F172A;font-size:14px;font-weight:700;line-height:1.4">{nom}</div>
  <div style="color:#94A3B8;font-size:12px;margin-top:3px">Quantité : {qte}</div>
</td>
<td style="padding:12px 0;border-bottom:1px solid #F1F5F9;text-align:right;vertical-align:middle;color:#0F172A;font-size:14px;font-weight:800;white-space:nowrap">
  {prix:,.0f} F
</td>
</tr>"""
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F8FAFC;border-radius:14px;border:1px solid #E2E8F0;margin:16px 0">
<tr>
<td style="padding:18px 22px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{rows}
<tr>
<td style="padding:14px 0 0;color:#0F172A;font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:.5px">Total</td>
<td style="padding:14px 0 0;text-align:right;color:#059669;font-size:20px;font-weight:900;white-space:nowrap">TOTAL_PLACEHOLDER</td>
</tr>
</table>
</td>
</tr>
</table>"""


def email_revendeur_nouvelle_commande(to_email, nom_revendeur, nom_boutique,
                                       reference, client_nom, client_telephone,
                                       produits, total, mode_paiement,
                                       lien_commandes):
    paiement_label = {
        "cash": "Paiement à la livraison",
        "mtn": "MTN Mobile Money",
        "orange": "Orange Money",
    }.get(mode_paiement, mode_paiement)

    info_box = _box([
        ("Référence", f'<span style="font-family:monospace">{reference}</span>'),
        ("Client", client_nom),
        ("Téléphone", client_telephone),
        ("Paiement", paiement_label),
    ])

    produits_html = _produits_table(produits).replace("TOTAL_PLACEHOLDER", f"{total:,.0f} FCFA")

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_revendeur}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">🎉 Vous venez de recevoir une <strong style="color:#0F172A">nouvelle commande</strong> sur votre boutique <strong style="color:#0F172A">{nom_boutique}</strong> !</p>

{info_box}

<div style="color:#0F172A;font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;margin-top:24px;margin-bottom:4px">Détail des produits</div>
{produits_html}

{_btn("Voir la commande", lien_commandes, "#10B981", "#059669")}

<p style="color:#94A3B8;font-size:13px;text-align:center;margin-top:12px">Contactez le client rapidement pour confirmer la commande.</p>
"""

    return _send(
        to_email,
        f"🛒 Nouvelle commande {reference} — {total:,.0f} FCFA",
        _template("Nouvelle commande reçue !", contenu, "#10B981", "#059669", emoji="🛒")
    )


def email_revendeur_paiement_recu(to_email, nom_revendeur, nom_boutique,
                                   reference, montant, methode, lien_commandes):
    methode_label = {
        "cash": "Paiement à la livraison",
        "mtn": "MTN Mobile Money",
        "orange": "Orange Money",
    }.get(methode, methode)

    info_box = _box([
        ("Référence", f'<span style="font-family:monospace">{reference}</span>'),
        ("Montant", f'<span style="color:#059669;font-size:16px">{montant:,.0f} FCFA</span>'),
        ("Méthode", methode_label),
    ])

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_revendeur}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">💰 Vous avez reçu un <strong style="color:#0F172A">paiement</strong> sur votre boutique <strong style="color:#0F172A">{nom_boutique}</strong> !</p>

{info_box}

{_btn("Voir la commande", lien_commandes, "#10B981", "#059669")}
"""

    return _send(
        to_email,
        f"💰 Paiement reçu — {montant:,.0f} FCFA",
        _template("Paiement reçu !", contenu, "#10B981", "#059669", emoji="💰")
    )


def email_revendeur_nouvel_avis(to_email, nom_revendeur, nom_boutique,
                                  client_nom, note, commentaire, lien_avis):
    etoiles = "★" * note + "☆" * (5 - note)

    info_box = _box([
        ("Client", client_nom),
        ("Note", f'<span style="color:#F59E0B;font-size:18px;letter-spacing:2px">{etoiles}</span> ({note}/5)'),
    ])

    commentaire_html = ""
    if commentaire:
        commentaire_html = f"""<div style="background:#FFFBEB;border-left:4px solid #F59E0B;border-radius:12px;padding:16px 20px;margin:16px 0">
<p style="color:#78350F;font-size:14px;line-height:1.7;margin:0;font-style:italic">"{commentaire}"</p>
</div>"""

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_revendeur}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">⭐ Un client vient de laisser un <strong style="color:#0F172A">avis</strong> sur votre boutique <strong style="color:#0F172A">{nom_boutique}</strong> !</p>

{info_box}
{commentaire_html}

{_btn("Voir les avis", lien_avis, "#F59E0B", "#D97706")}
"""

    return _send(
        to_email,
        f"⭐ Nouvel avis {note}/5 de {client_nom}",
        _template("Nouvel avis client !", contenu, "#F59E0B", "#D97706", emoji="⭐")
    )


def email_revendeur_nouveau_client(to_email, nom_revendeur, nom_boutique,
                                     client_email, client_pays, lien_clients):
    info_box = _box([
        ("Email", client_email),
        ("Pays", client_pays or "Non renseigné"),
    ])

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_revendeur}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">👤 Un <strong style="color:#0F172A">nouveau client</strong> s'est inscrit via votre boutique <strong style="color:#0F172A">{nom_boutique}</strong> !</p>

{info_box}

{_btn("Voir mes clients", lien_clients, "#7C3AED", "#6D28D9")}
"""

    return _send(
        to_email,
        f"👤 Nouveau client — {client_email}",
        _template("Nouveau client inscrit !", contenu, "#7C3AED", "#6D28D9", emoji="👤")
    )


def email_revendeur_resume_quotidien(to_email, nom_revendeur, nom_boutique,
                                       nb_commandes, total_ventes, nb_nouveaux_clients,
                                       lien_dashboard):
    info_box = _box([
        ("Commandes reçues", f'<span style="color:#059669;font-size:16px">{nb_commandes}</span>'),
        ("Chiffre d'affaires", f'<span style="color:#059669;font-size:16px">{total_ventes:,.0f} FCFA</span>'),
        ("Nouveaux clients", f'<span style="color:#0096C7;font-size:16px">{nb_nouveaux_clients}</span>'),
    ])

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_revendeur}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">📊 Voici votre <strong style="color:#0F172A">résumé du jour</strong> pour la boutique <strong style="color:#0F172A">{nom_boutique}</strong> :</p>

{info_box}

{_btn("Voir mon dashboard", lien_dashboard, "#0066FF", "#0047CC")}
"""

    return _send(
        to_email,
        f"📊 Résumé du jour — {nb_commandes} commande(s)",
        _template("Résumé de votre journée", contenu, "#0066FF", "#0047CC", emoji="📊")
    )


def email_revendeur_stock_bas(to_email, nom_revendeur, nom_boutique,
                                produit_nom, stock_restant, lien_produits):
    info_box = _box([
        ("Produit", produit_nom),
        ("Stock restant", f'<span style="color:#DC2626;font-size:16px">{stock_restant} unité(s)</span>'),
    ])

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_revendeur}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">🚨 Attention ! Un produit de votre boutique <strong style="color:#0F172A">{nom_boutique}</strong> est presque en rupture de stock.</p>

{info_box}

{_btn("Gérer mon stock", lien_produits, "#DC2626", "#991B1B")}
"""

    return _send(
        to_email,
        f"🚨 Stock bas — {produit_nom}",
        _template("Alerte stock bas !", contenu, "#DC2626", "#991B1B", emoji="🚨")
    )


def email_client_confirmation_commande(to_email, nom_client, nom_boutique,
                                         reference, produits, total,
                                         lien_confirmation, whatsapp_vendeur):
    info_box = _box([
        ("Référence", f'<span style="font-family:monospace">{reference}</span>'),
        ("Boutique", nom_boutique),
    ])

    produits_html = _produits_table(produits).replace("TOTAL_PLACEHOLDER", f"{total:,.0f} FCFA")

    wa_btn = ""
    if whatsapp_vendeur:
        wa_btn = f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px auto 0">
<tr>
<td align="center" style="border-radius:14px;background:#25D366">
<a href="https://wa.me/{whatsapp_vendeur}" target="_blank" style="display:inline-block;padding:14px 32px;color:#ffffff;text-decoration:none;font-weight:800;font-size:14px;border-radius:14px">Contacter le vendeur sur WhatsApp</a>
</td>
</tr>
</table>"""

    contenu = f"""
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 14px">Bonjour <strong style="color:#0F172A">{nom_client}</strong>,</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">✅ Merci pour votre commande sur <strong style="color:#0F172A">{nom_boutique}</strong> !</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px">Votre commande a bien été enregistrée. Le vendeur va vous contacter rapidement pour la livraison.</p>

{info_box}

<div style="color:#0F172A;font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;margin-top:24px;margin-bottom:4px">Vos produits</div>
{produits_html}

{_btn("Voir ma commande", lien_confirmation, "#10B981", "#059669")}
{wa_btn}

<p style="color:#94A3B8;font-size:13px;text-align:center;margin-top:20px">Une question ? Contactez le vendeur sur WhatsApp.</p>
"""

    return _send(
        to_email,
        f"✅ Commande {reference} confirmée",
        _template("Commande confirmée !", contenu, "#10B981", "#059669", emoji="✅")
    )