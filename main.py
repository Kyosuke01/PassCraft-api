from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import random
import string
import requests
import os
import time
from upstash_redis import AsyncRedis
from dotenv import load_dotenv
load_dotenv()

# Connexion Redis Upstash
redis = AsyncRedis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

app = FastAPI()

ALLOWED_ORIGINS = [
    "https://passcraft.fr",
    "https://www.passcraft.fr",
]

# CORS Middleware restreint aux origines autorisées
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CURRENT_VERSION = "1.1.1"

@app.get("/")
def read_root():
    return {"message": "PassCraft API fonctionne"}

@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join("static", "favicon.ico"))

@app.get("/check-update")
def check_for_updates():
    try:
        version_url = "https://raw.githubusercontent.com/Kyosuke01/PassCraft/main/version.txt"
        response = requests.get(version_url)
        latest_version = response.text.strip()

        if latest_version != CURRENT_VERSION:
            return {
                "update": True,
                "latest_version": latest_version,
                "download_url": "https://github.com/Kyosuke01/PassCraft/releases/latest"
            }
        else:
            return {"update": False, "latest_version": CURRENT_VERSION}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur de connexion : {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur inconnue : {e}")

def generate_password(
    length: int,
    use_lowercase: bool = True,
    use_uppercase: bool = True,
    use_numbers: bool = True,
    use_special: bool = True
) -> str:
    if length <= 0:
        raise ValueError("La longueur doit être supérieure à zéro.")

    char_pools = {
        "lowercase": string.ascii_lowercase if use_lowercase else "",
        "uppercase": string.ascii_uppercase if use_uppercase else "",
        "numbers": string.digits if use_numbers else "",
        "special": "!@#$%^&*()-_=+[]{}|;:,.<>?" if use_special else "",
    }

    active_pools = [pool for pool in char_pools.values() if pool]

    if not active_pools:
        raise ValueError("Sélectionnez au moins un type de caractère.")

    if length < len(active_pools):
        selected_pools = random.sample(active_pools, length)
    else:
        selected_pools = active_pools

    selected_chars = [random.choice(pool) for pool in selected_pools]

    remaining_length = length - len(selected_chars)
    all_chars = "".join(active_pools)

    if remaining_length > 0:
        selected_chars.extend(random.choices(all_chars, k=remaining_length))

    random.shuffle(selected_chars)

    return "".join(selected_chars)

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 30

async def is_rate_limited(ip: str) -> bool:
    key = f"rate_limit:{ip}"

    # incrémente le compteur atomiquement, crée la clé si inexistante
    count = await redis.incr(key)

    if count == 1:
        # si première requête, on fixe la TTL
        await redis.expire(key, RATE_LIMIT_WINDOW)

    if count > RATE_LIMIT_MAX_REQUESTS:
        return True

    return False


@app.get("/generate")
async def api_generate_password(
    request: Request,
    length: int = Query(..., gt=0, le=1000),
    lowercase: bool = True,
    uppercase: bool = True,
    numbers: bool = True,
    special: bool = True,
):
    origin = request.headers.get("origin")
    print("Origine reçu :", origin)

    if origin not in ALLOWED_ORIGINS:
        print("Origine refusée :", origin)
        raise HTTPException(status_code=403, detail="Origine non autorisée")

    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host

    if await is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Trop de requêtes. Réessayez plus tard.")

    try:
        password = generate_password(
            length=length,
            use_lowercase=lowercase,
            use_uppercase=uppercase,
            use_numbers=numbers,
            use_special=special,
        )
        return {"password": password}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
