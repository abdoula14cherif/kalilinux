# ═══════════════════════════════════════════════════════════════
# CREDIT BOOST — GESTION ADMIN (AVEC DEBUG)
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/credit-boost")
@login_required
def credit_boost():
    """Vue globale de tous les Credit Boost."""
    profile, redir = _require_admin()
    if redir:
        return redir

    # Stats
    stats = get_stats_globales()

    # Revendeurs avec credit faible
    revendeurs_faibles = get_revendeurs_credit_faible(seuil=2000, limit=100)

    # Dernieres transactions
    transactions = get_transactions_credit_boost_admin(limit=100)

    return render_template("dashboard/admin/credit_boost.html",
                          profile=profile,
                          stats=stats,
                          revendeurs_faibles=revendeurs_faibles,
                          transactions=transactions)


@dashboard_admin_bp.route("/revendeurs/<user_id>/credit")
@login_required
def revendeur_credit(user_id):
    """Detail du Credit Boost d'un revendeur."""
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    revendeur = get_profile(user_id)
    if not revendeur:
        flash("Revendeur introuvable.", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    transactions = get_transactions_credit_boost_admin(user_id=user_id, limit=100)

    return render_template("dashboard/admin/revendeur_credit.html",
                          profile=profile,
                          revendeur=revendeur,
                          transactions=transactions)


@dashboard_admin_bp.route("/revendeurs/<user_id>/credit/ajouter", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def revendeur_credit_ajouter(user_id):
    """
    Ajoute du Credit Boost manuellement.
    VERSION DEBUG : logs détaillés + flash des infos techniques.
    """
    profile, redir = _require_admin()
    if redir:
        return redir

    # ─── DEBUG ÉTAPE 1 : UUID reçu ───────────────────────────
    logger.warning(f"╔═══ [CREDIT AJOUTER] START ═══")
    logger.warning(f"║ user_id RAW reçu du form : {user_id!r}")

    from app.models.admin import ajouter_credit_boost, _valider_uuid, _headers, _url
    import requests as req_lib

    uid_valid = _valider_uuid(user_id, "user_id")
    logger.warning(f"║ user_id APRÈS _valider_uuid : {uid_valid!r}")

    if not uid_valid:
        logger.warning(f"╚═══ ABORT : UUID invalide ═══")
        flash(f"UUID invalide : {user_id}", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    # ─── DEBUG ÉTAPE 2 : Test direct Supabase ────────────────
    try:
        # Test 1 : sans select (pour voir tout)
        url_test = _url(f"profiles?id=eq.{uid_valid}&limit=1")
        logger.warning(f"║ Test GET URL : {url_test}")

        r_test = req_lib.get(url_test, headers=_headers(), timeout=10)
        logger.warning(f"║ Test GET status : {r_test.status_code}")
        logger.warning(f"║ Test GET body : {r_test.text[:500]}")

        # Stocker pour flash
        debug_info = f"GET status={r_test.status_code} | body={r_test.text[:300]}"

        if r_test.status_code >= 300:
            logger.error(f"╚═══ ABORT : Supabase error {r_test.status_code} ═══")
            flash(f"❌ Supabase error {r_test.status_code}", "error")
            flash(f"Réponse : {r_test.text[:300]}", "warning")
            return redirect(url_for("dashboard_admin.credit_boost"))

        data = r_test.json()
        logger.warning(f"║ Type réponse : {type(data).__name__}")
        logger.warning(f"║ Nombre résultats : {len(data) if isinstance(data, list) else 'N/A'}")

        if isinstance(data, list) and len(data) > 0:
            logger.warning(f"║ Profil trouvé : id={data[0].get('id')} email={data[0].get('email')}")
            logger.warning(f"║ credit_boost actuel : {data[0].get('credit_boost')}")
        elif isinstance(data, list) and len(data) == 0:
            logger.warning(f"║ AUCUN profil avec cet ID !")
            flash(f"❌ Aucun profil avec l'ID {uid_valid}", "error")
            flash("Vérifie que cet utilisateur existe bien dans la table profiles", "info")
            return redirect(url_for("dashboard_admin.credit_boost"))
        elif isinstance(data, dict):
            logger.warning(f"║ Réponse dict (erreur probable) : {data}")
            flash(f"❌ Erreur Supabase : {data.get('message', str(data))[:200]}", "error")
            return redirect(url_for("dashboard_admin.credit_boost"))

    except Exception as e:
        logger.exception(f"╚═══ ABORT : Exception test GET ═══")
        flash(f"❌ Exception test : {type(e).__name__} - {str(e)[:200]}", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    # ─── DEBUG ÉTAPE 3 : Récupérer les paramètres du formulaire ───
    montant = request.form.get("montant", "").strip()
    raison = request.form.get("raison", "").strip()
    logger.warning(f"║ montant = {montant!r}")
    logger.warning(f"║ raison = {raison!r}")

    # ─── DEBUG ÉTAPE 4 : Appel effectif ─────────────────────
    ok, err = ajouter_credit_boost(user_id, montant, raison)
    logger.warning(f"║ ajouter_credit_boost résultat : ok={ok} err={err!r}")

    if ok:
        log_admin_action(profile["id"], "credit_boost_ajout",
                        cible_type="user", cible_id=uid_valid,
                        details={"montant": montant, "raison": raison[:100]},
                        ip=_ip())
        flash(f"✅ Credit Boost ajoute : +{float(montant):,.0f} FCFA", "success")
        logger.warning(f"╚═══ SUCCESS ═══")
    else:
        flash(f"❌ Erreur : {err}", "error")
        # Afficher le debug en plus
        flash(f"🔍 Debug : {debug_info}", "warning")
        logger.warning(f"╚═══ FAILED : {err} ═══")

    return redirect(url_for("dashboard_admin.revendeur_credit", user_id=uid_valid))


@dashboard_admin_bp.route("/revendeurs/<user_id>/credit/deduire", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def revendeur_credit_deduire(user_id):
    """
    Deduit du Credit Boost manuellement.
    VERSION DEBUG.
    """
    profile, redir = _require_admin()
    if redir:
        return redir

    logger.warning(f"╔═══ [CREDIT DEDUIRE] START ═══")
    logger.warning(f"║ user_id RAW : {user_id!r}")

    uid_valid = _valider_uuid(user_id, "user_id")
    logger.warning(f"║ user_id VALIDÉ : {uid_valid!r}")

    if not uid_valid:
        flash(f"UUID invalide : {user_id}", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    # Test Supabase direct
    from app.models.admin import deduire_credit_boost, _headers, _url
    import requests as req_lib

    try:
        r_test = req_lib.get(
            _url(f"profiles?id=eq.{uid_valid}&limit=1"),
            headers=_headers(), timeout=10
        )
        logger.warning(f"║ Test GET status : {r_test.status_code}")
        logger.warning(f"║ Test GET body : {r_test.text[:500]}")

        if r_test.status_code >= 300:
            flash(f"❌ Supabase error {r_test.status_code}", "error")
            flash(f"Réponse : {r_test.text[:300]}", "warning")
            return redirect(url_for("dashboard_admin.credit_boost"))

        data = r_test.json()
        if isinstance(data, list) and len(data) == 0:
            flash(f"❌ Aucun profil avec l'ID {uid_valid}", "error")
            return redirect(url_for("dashboard_admin.credit_boost"))

    except Exception as e:
        logger.exception(f"Exception test : {e}")
        flash(f"❌ Exception : {type(e).__name__}", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    montant = request.form.get("montant", "").strip()
    raison = request.form.get("raison", "").strip()

    ok, err = deduire_credit_boost(user_id, montant, raison)
    logger.warning(f"║ deduire résultat : ok={ok} err={err!r}")

    if ok:
        log_admin_action(profile["id"], "credit_boost_deduction",
                        cible_type="user", cible_id=uid_valid,
                        details={"montant": montant, "raison": raison[:100]},
                        ip=_ip())
        flash(f"✅ Credit Boost deduit : -{float(montant):,.0f} FCFA", "warning")
        logger.warning(f"╚═══ SUCCESS ═══")
    else:
        flash(f"❌ Erreur : {err}", "error")
        logger.warning(f"╚═══ FAILED ═══")

    return redirect(url_for("dashboard_admin.revendeur_credit", user_id=uid_valid))