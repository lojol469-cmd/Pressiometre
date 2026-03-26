"""
Interface KIBALI — Mistral-7B géophysique en 4-bit (BitsAndBytes NF4)
Chargement paresseux optimisé RTX 5090.
"""
from __future__ import annotations
import threading
from pathlib import Path
from typing import Optional

MODEL_PATH = Path(__file__).parent.parent / "kibali-final-merged"

_model = None
_tokenizer = None
_load_error: Optional[str] = None
_lock = threading.Lock()


def _do_load():
    global _model, _tokenizer, _load_error
    try:
        import time as _time
        import torch
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        )
        print("[KIBALI] ── Démarrage du chargement ──", flush=True)
        print(f"[KIBALI] Chemin modèle : {MODEL_PATH}", flush=True)

        print("[KIBALI] Chargement du tokenizer…", flush=True)
        t0 = _time.time()
        _tokenizer = AutoTokenizer.from_pretrained(
            str(MODEL_PATH), local_files_only=True
        )
        print(f"[KIBALI] Tokenizer chargé ✅  ({_time.time()-t0:.1f}s)", flush=True)

        print("[KIBALI] Configuration BitsAndBytes NF4 4-bit…", flush=True)
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        print(f"[KIBALI] GPU détecté : {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU (fallback)'}", flush=True)
        print("[KIBALI] Chargement modèle Mistral-7B NF4 4-bit (patience…)", flush=True)
        t1 = _time.time()
        _model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_PATH),
            quantization_config=bnb_config,
            device_map="auto",
            local_files_only=True,
        )
        _model.eval()
        print(f"[KIBALI] Modèle chargé ✅  ({_time.time()-t1:.1f}s)", flush=True)
        print(f"[KIBALI] Prêt — total {_time.time()-t0:.1f}s ✅", flush=True)
    except Exception as e:
        print(f"[KIBALI] ERREUR chargement ❌ : {e}", flush=True)
        _load_error = str(e)


def load_async():
    """Démarre le chargement en arrière-plan."""
    t = threading.Thread(target=_do_load, daemon=True)
    t.start()


def is_ready() -> bool:
    with _lock:
        return _model is not None


def get_error() -> Optional[str]:
    return _load_error


def ask(question: str, context: str = "", max_tokens: int = 512) -> str:
    """
    Interroge KIBALI. Si le modèle n'est pas encore chargé, tente un chargement
    synchrone une seule fois.
    """
    global _model, _tokenizer, _load_error

    if _model is None:
        if _load_error:
            return f"[KIBALI non disponible] {_load_error}"
        _do_load()
        if _model is None:
            return f"[KIBALI non disponible] {_load_error}"

    import torch
    SYSTEM = (
        "Tu es KIBALI, ingénieur géotechnicien expert spécialisé dans l'essai pressiométrique "
        "Ménard (NF P 94-110). Tu parles UNIQUEMENT en français.\n\n"
        "TES CAPACITÉS :\n"
        "• Tu as accès aux données pressiométriques RÉELLES de la session courante (fournies dans le contexte).\n"
        "• Tu analyses courbes P-V, modules Em, pressions Pl et Pf, rapports Em/Pl.\n"
        "• Tu détectes et expliques les anomalies pressiométriques RÉELLES.\n"
        "• Tu calcules capacité portante, tassements et contraintes admissibles selon NF P 94-110.\n"
        "• Tu évalues la qualité des essais (grades A/B/C/D) sur la base des données réelles.\n"
        "• Tu identifies le type de sol et l'état de consolidation (NC/SC) selon la classification Ménard.\n"
        "• Tu fournis des recommandations de fondation adaptées (superficielle, profonde) avec calculs.\n"
        "• Tu évalues les risques géotechniques (tassement différentiel, liquéfaction, portance).\n\n"
        "RÈGLES ABSOLUES :\n"
        "• Utilise TOUJOURS les données réelles fournies dans le contexte — ne cite jamais des valeurs fictives.\n"
        "• Si le contexte contient des données d'essai, base ton analyse exclusivement dessus.\n"
        "• Sois précis, concis et professionnel. Montre les calculs quand demandé.\n"
        "• Si une question porte sur une donnée absente du contexte, dis-le clairement.\n"
        "• Cite les articles et formules NF P 94-110 quand pertinent.\n"
        "• Structure tes réponses avec des sections claires (##Titre) quand la réponse est longue."
    )
    if context:
        prompt = (
            f"[INST] <<SYS>>\n{SYSTEM}\n<</SYS>>\n\n"
            f"Contexte des données :\n{context}\n\n"
            f"Question : {question} [/INST]"
        )
    else:
        prompt = f"[INST] <<SYS>>\n{SYSTEM}\n<</SYS>>\n\n{question} [/INST]"

    with _lock:
        assert _tokenizer is not None
        inputs = _tokenizer(
            prompt, return_tensors="pt",
            truncation=True, max_length=4096
        ).to(_model.device)
        with torch.no_grad():
            outputs = _model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                pad_token_id=_tokenizer.eos_token_id,
            )
        full = _tokenizer.decode(outputs[0], skip_special_tokens=True)

    if "[/INST]" in full:
        return full.split("[/INST]", 1)[-1].strip()
    return full.strip()
