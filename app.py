import os
import json
import anthropic
import requests
from flask import Flask, request, jsonify, render_template_string
app = Flask(__name__)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "Eres el asistente virtual del CAMM.")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
# Límite de historial: solo los últimos 10 mensajes se envían a Claude
HISTORY_LIMIT = 10
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
processed_messages = set()
paused_conversations = {}   # {sender_id: nombre}
recent_conversations = {}   # {sender_id: nombre}
AVISO_PRIVACIDAD = (
    "👋 Bienvenido/a al asistente virtual del CAMM "
    "(Centro de Actualización del Magisterio de Monterrey).\n\n"
    "ℹ️ Esta conversación puede ser utilizada con fines de mejora "
    "del servicio e investigación institucional, conforme a nuestra "
    "política de privacidad:\n"
    "https://sites.google.com/view/cam-mty/aviso-de-privacidad\n\n"
)
CATEGORIAS = [
    "Cursos de actualización",
    "Diplomados",
    "Talleres",
    "Licenciatura",
    "Posgrado",
    "Constancias y certificados",
    "Inscripción y requisitos",
    "Costos y pagos",
    "Horarios y fechas",
    "Eventos",
    "Queja o insatisfacción",
    "Sin relevancia institucional"
]
SUBCATEGORIAS = [
    "Costos",
    "Inscripción y requisitos",
    "Plan de estudios",
    "Fechas y horarios",
    "Constancias",
    "Contenido del curso",
    "Proceso de pago",
    "Verificación oficial",
    "Derivación a humano",
    "No aplica"
]
# Mensajes cortos sin valor de clasificación para la investigación
MENSAJES_TRIVIALES = {
    "hola", "hi", "hello", "buenas", "buenos días", "buenas tardes",
    "buenas noches", "ok", "okay", "okey", "gracias", "muchas gracias",
    "si", "sí", "no", "bye", "adios", "adiós", "hasta luego",
    "entendido", "claro", "perfecto", "excelente", "de acuerdo",
    "está bien", "esta bien", "listo", "dale", "va", "👍", "ok gracias",
    "gracias!", "sí, gracias", "si, gracias", "muy bien", "bien"
}
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Panel de seguimiento — CAMM Chatbot</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f4f6f9; color: #1a1a1a; padding: 24px; }
  h1 { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
  .subtitle { font-size: 13px; color: #666; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; }
  .actions { display: flex; gap: 12px; }
  .section { background: white; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 20px; overflow: hidden; }
  .section-header { padding: 14px 18px; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #e0e0e0; display: flex; align-items: center; gap: 8px; }
  .section-header.pausadas { background: #fff4e5; color: #b45309; border-color: #fcd89a; }
  .section-header.activas { background: #f0fdf4; color: #166534; border-color: #bbf7d0; }
  .row { display: flex; align-items: center; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid #f0f0f0; }
  .row:last-child { border-bottom: none; }
  .name { font-size: 14px; font-weight: 500; }
  .sid { font-size: 11px; color: #999; margin-top: 2px; font-family: monospace; }
  .btn { padding: 6px 14px; border-radius: 6px; border: none; font-size: 13px; font-weight: 500; cursor: pointer; text-decoration: none; display: inline-block; }
  .btn-pause  { background: #fff4e5; color: #b45309; border: 1px solid #fcd89a; }
  .btn-pause:hover  { background: #fde68a; }
  .btn-resume { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
  .btn-resume:hover { background: #bbf7d0; }
  .btn-sync   { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; font-size: 12px; padding: 5px 12px; }
  .btn-sync:hover   { background: #dbeafe; }
  .btn-reload { background: transparent; color: #999; border: none; font-size: 12px; padding: 5px 0; text-decoration: none; }
  .btn-reload:hover { color: #333; }
  .empty { padding: 16px 18px; font-size: 13px; color: #999; }
  .badge { display: inline-block; background: #fee2e2; color: #991b1b; border-radius: 99px; font-size: 11px; font-weight: 600; padding: 2px 8px; }
  .badge.green { background: #dcfce7; color: #166534; }
  .sync-msg { font-size: 12px; color: #1d4ed8; margin-bottom: 16px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 8px 14px; }
</style>
</head>
<body>
<h1>Panel de seguimiento — CAMM Chatbot</h1>
<div class="subtitle">
  <span>Pausa el bot para atender personalmente una conversación. Al reanudar, el bot vuelve a responder.</span>
  <div class="actions">
    <a class="btn btn-sync" href="/admin/sync?token={{ token }}">↺ Sincronizar nombres</a>
    <a class="btn-reload" href="/admin?token={{ token }}">↻ Actualizar</a>
  </div>
</div>
{% if synced %}
<div class="sync-msg">Nombres sincronizados desde Google Sheets.</div>
{% endif %}
<div class="section">
  <div class="section-header pausadas">
    En seguimiento humano
    <span class="badge">{{ pausadas|length }}</span>
  </div>
  {% if pausadas %}
    {% for sid, nombre in pausadas.items() %}
    <div class="row">
      <div>
        <div class="name">{{ nombre }}</div>
        <div class="sid">{{ sid }}</div>
      </div>
      <a class="btn btn-resume" href="/admin/reanudar?id={{ sid }}&token={{ token }}">Reanudar bot</a>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">Ninguna conversación pausada.</div>
  {% endif %}
</div>
<div class="section">
  <div class="section-header activas">
    Conversaciones recientes
    <span class="badge green">{{ activas|length }}</span>
  </div>
  {% if activas %}
    {% for sid, nombre in activas.items() %}
    <div class="row">
      <div>
        <div class="name">{{ nombre }}</div>
        <div class="sid">{{ sid }}</div>
      </div>
      <a class="btn btn-pause" href="/admin/pausa?id={{ sid }}&token={{ token }}">Tomar seguimiento</a>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">Sin conversaciones recientes aún.</div>
  {% endif %}
</div>
</body>
</html>
"""
def limpiar_json(raw):
    """Extrae JSON limpio de una respuesta que puede incluir bloques ```json ... ```."""
    raw = raw.strip()
    if "```" in raw:
        partes = raw.split("```")
        for parte in partes:
            parte = parte.strip()
            if parte.startswith("json"):
                parte = parte[4:].strip()
            if parte.startswith("{"):
                return parte
    return raw
def es_trivial(texto):
    """Detecta mensajes cortos sin valor de clasificación para la investigación."""
    return texto.strip().lower() in MENSAJES_TRIVIALES
def clasificar_mensaje(user_message, history=None):
    try:
        contexto = ""
        if history and len(history) > 1:
            ultimos = history[-4:-1]
            lineas = []
            for m in ultimos:
                rol = "Usuario" if m["role"] == "user" else "Bot"
                lineas.append(f"{rol}: {m['content'][:120]}")
            if lineas:
                contexto = "\nContexto previo de la conversación:\n" + "\n".join(lineas) + "\n"
        prompt = f"""Eres un clasificador para el CAMM (Centro de Actualización del Magisterio de Monterrey), institución pública de Nuevo León dedicada a la formación y actualización docente. Ofrece cursos de actualización, diplomados, talleres y programas educativos para maestros en servicio.
Clasifica este mensaje de un usuario del chatbot de Facebook del CAMM.
Responde ÚNICAMENTE con JSON con dos campos:
- "categoria": exactamente una de: {', '.join(CATEGORIAS)}
- "subcategoria": exactamente una de: {', '.join(SUBCATEGORIAS)}
Reglas:
- Mensajes sobre programas académicos, cursos, diplomados o talleres → categoría correspondiente al programa
- Mensajes sobre constancias, certificados o documentos → "Constancias y certificados"
- Mensajes cortos de continuación ("sí", "ok", "gracias", "entendido") → usa el contexto previo para inferir la categoría correcta
- Solo usa "Sin relevancia institucional" si el mensaje es claramente ajeno a educación o al CAMM
{contexto}
Mensaje a clasificar: "{user_message}"
Responde SOLO el JSON, sin explicación ni bloques de código. Ejemplo:
{{"categoria":"Cursos de actualización","subcategoria":"Costos"}}"""
        result = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = result.content[0].text
        print(f"[clasificar] RAW: {raw!r} | mensaje: {user_message}")
        raw = limpiar_json(raw)
        data = json.loads(raw)
        categoria = data.get("categoria", "Sin relevancia institucional")
        subcategoria = data.get("subcategoria", "No aplica")
        if categoria not in CATEGORIAS:
            categoria = "Sin relevancia institucional"
        if subcategoria not in SUBCATEGORIAS:
            subcategoria = "No aplica"
        return categoria, subcategoria
    except Exception as e:
        print(f"[clasificar] ERROR: {e} | mensaje: {user_message}")
        return "Sin relevancia institucional", "No aplica"
def detectar_derivacion(bot_response):
    palabras_clave = [
        "llámanos", "llamanos", "escríbenos", "escribenos",
        "teléfono", "telefono", "correo", "818-374", "8183747217",
        "cam-mty", "subdirector", "director", "oficina"
    ]
    texto = bot_response.lower()
    for palabra in palabras_clave:
        if palabra in texto:
            return "Sí"
    return "No"
def get_history_from_sheets(sender_id):
    """Recupera historial y nombre del usuario desde Google Sheets."""
    try:
        response = requests.get(
            APPS_SCRIPT_URL,
            params={"action": "get_history", "sender_id": sender_id},
            timeout=5
        )
        data = response.json()
        nombre = data.get("nombre", "")
        if nombre and sender_id in recent_conversations:
            recent_conversations[sender_id] = nombre
        if nombre and sender_id in paused_conversations:
            paused_conversations[sender_id] = nombre
        return data.get("messages", []), nombre
    except Exception:
        return [], ""
def is_first_time_user(sender_id, history):
    if len(history) > 0:
        return False
    try:
        response = requests.get(
            APPS_SCRIPT_URL,
            params={"action": "check_user", "sender_id": sender_id},
            timeout=5
        )
        data = response.json()
        return not data.get("exists", False)
    except Exception:
        return False
def load_users_from_sheets():
    """Carga el listado de usuarios conocidos desde Sheets."""
    try:
        response = requests.get(
            APPS_SCRIPT_URL,
            params={"action": "get_users"},
            timeout=10
        )
        data = response.json()
        users = data.get("users", {})
        for sid, nombre in users.items():
            recent_conversations[sid] = nombre or sid
            if sid in paused_conversations:
                paused_conversations[sid] = nombre or sid
    except Exception:
        pass
# ── Rutas de administración ────────────────────────────────────────────────
@app.route("/admin")
def admin_panel():
    token = request.args.get("token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return "No autorizado.", 403
    synced = request.args.get("synced", "")
    activas = {sid: nombre for sid, nombre in recent_conversations.items()
               if sid not in paused_conversations}
    return render_template_string(
        ADMIN_HTML,
        pausadas=paused_conversations,
        activas=activas,
        token=token,
        synced=synced
    )
@app.route("/admin/sync")
def admin_sync():
    token = request.args.get("token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return "No autorizado.", 403
    load_users_from_sheets()
    return f"""<meta http-equiv="refresh" content="0;url=/admin?token={token}&synced=1">"""
@app.route("/admin/pausa")
def admin_pausa():
    token = request.args.get("token", "")
    sid = request.args.get("id", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return "No autorizado.", 403
    if sid:
        paused_conversations[sid] = recent_conversations.get(sid, sid)
    return f"""<meta http-equiv="refresh" content="0;url=/admin?token={token}">"""
@app.route("/admin/reanudar")
def admin_reanudar():
    token = request.args.get("token", "")
    sid = request.args.get("id", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return "No autorizado.", 403
    if sid:
        paused_conversations.pop(sid, None)
    return f"""<meta http-equiv="refresh" content="0;url=/admin?token={token}">"""
# ── Webhook ────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403
@app.route("/webhook", methods=["POST"])
def handle_message():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and not event["message"].get("is_echo"):
                    message_id = event["message"].get("mid", "")
                    if message_id in processed_messages:
                        continue
                    processed_messages.add(message_id)
                    sender_id = event["sender"]["id"]
                    text = event["message"].get("text", "")
                    if not text:
                        continue
                    if sender_id not in recent_conversations:
                        recent_conversations[sender_id] = sender_id
                    if sender_id in paused_conversations:
                        continue
                    history, nombre = get_history_from_sheets(sender_id)
                    if nombre:
                        recent_conversations[sender_id] = nombre
                    is_new_user = is_first_time_user(sender_id, history)
                    reply, tokens = get_claude_response(sender_id, text, history)
                    if es_trivial(text):
                        categoria, subcategoria = "Sin relevancia institucional", "No aplica"
                    else:
                        categoria, subcategoria = clasificar_mensaje(text, history)
                    derivacion = detectar_derivacion(reply)
                    if is_new_user:
                        send_message(sender_id, AVISO_PRIVACIDAD)
                    send_message(sender_id, reply)
                    log_conversation(sender_id, text, reply, tokens, categoria, subcategoria, derivacion)
    return jsonify({"status": "ok"}), 200
def get_claude_response(sender_id, user_message, history):
    try:
        history.append({"role": "user", "content": user_message})
        history_reciente = history[-HISTORY_LIMIT:] if len(history) > HISTORY_LIMIT else history
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=history_reciente,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        reply = message.content[0].text
        tokens = message.usage.input_tokens + message.usage.output_tokens
        return reply, tokens
    except Exception as e:
        print(f"[claude] ERROR: {e}")
        return "Gracias por tu mensaje. En breve un asesor del CAMM te contactará.", 0
def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v19.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, headers=headers, params=params, json=data)
def log_conversation(sender_id, user_message, bot_response, tokens_used, categoria, subcategoria, derivacion_humano):
    try:
        payload = {
            "sender_id": sender_id,
            "user_message": user_message,
            "bot_response": bot_response,
            "tokens_used": tokens_used,
            "categoria": categoria,
            "subcategoria": subcategoria,
            "derivacion_humano": derivacion_humano
        }
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=5)
    except Exception:
        pass
if __name__ == "__main__":
    load_users_from_sheets()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
