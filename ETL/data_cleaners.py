import re
import unicodedata
import pandas as pd
from thefuzz import fuzz, process


def normalize_text(text: str) -> str | None:
    """
    Normaliza una cadena de texto:
    - Convierte a mayúsculas.
    - Elimina tildes/acentos.
    - Elimina espacios extra y recorta.
    """
    if not isinstance(text, str):
        return None  # Devolver None si no es string o es None

    text = text.upper()
    text = str(
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text if text != "" else None  # Devolver None si queda vacío


def extract_first_name_and_surname(name: str | None) -> str | None:
    """
    Extrae el primer nombre y el primer apellido de una cadena.
    Asume que el input ya está normalizado (mayúsculas, sin tildes, sin espacios extra).
    """
    if not isinstance(name, str) or not name:
        return None  # Devolver None si no es string o está vacío

    words = name.split()
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    elif len(words) == 1:
        return words[0]
    return None  # Devolver None si no se puede extraer


def apply_fuzzy_matching_to_cobrador(
    df: pd.DataFrame, threshold: int = 85
) -> pd.DataFrame:
    """
    Aplica normalización y fuzzy matching a la columna 'cobrador' de un DataFrame.
    - Normaliza el texto (mayúsculas, sin tildes, sin espacios extra).
    - Identifica nombres similares utilizando fuzzy matching (umbral 85%).
    - Reemplaza nombres similares por el primer nombre encontrado como canónico.
    """
    col_name = "cobrador"  # Hardcodeado a cobrador según la instrucción del usuario
    if col_name not in df.columns:
        print(f"Advertencia: La columna '{col_name}' no se encontró en el DataFrame.")
        return df

    print(f"Aplicando limpieza y fuzzy matching a la columna '{col_name}'...")

    # 1. Normalización y creación de claves difusas
    df["_normalized_cobrador"] = df[col_name].apply(normalize_text)
    df["_fuzzy_key"] = df["_normalized_cobrador"].apply(extract_first_name_and_surname)

    # Crear un mapeo de claves difusas a nombres canónicos
    unique_keys = df["_fuzzy_key"].dropna().unique()
    canonical_map = {}

    for key in unique_keys:
        if key in canonical_map:  # Ya procesado
            continue

        # Encontrar coincidencias difusas usando token_set_ratio
        potential_matches_keys = [
            k for k in unique_keys if fuzz.token_set_ratio(key, k) >= threshold
        ]

        # Seleccionar el primer nombre ORIGINAL (no normalizado) como canónico
        # Buscamos en los valores de la columna original 'cobrador' que generaron estas claves difusas
        # Convertir a lista y ordenar para asegurar que siempre se elija el "primero" de manera consistente
        candidates_for_canonical = (
            df[df["_fuzzy_key"].isin(potential_matches_keys)][col_name]
            .dropna()
            .unique()
            .tolist()
        )
        candidates_for_canonical.sort()  # Ordenar para consistencia en la selección del "primero"

        if candidates_for_canonical:
            canonical_name = candidates_for_canonical[0]
        else:
            # Fallback: si por alguna razón no se encuentra un original, usar la clave normalizada
            canonical_name = key

        # Asignar el nombre canónico a todas las claves que coinciden
        for match_key in potential_matches_keys:
            canonical_map[match_key] = canonical_name

    # Aplicar el mapeo al DataFrame en la columna original 'cobrador'
    # Usar .fillna(df[col_name]) para mantener los valores originales si no hubo match difuso
    df[col_name] = df["_fuzzy_key"].map(canonical_map).fillna(df[col_name])

    # Eliminar columnas temporales
    df = df.drop(columns=["_normalized_cobrador", "_fuzzy_key"])

    print(f"✅ Limpieza de la columna '{col_name}' completada.")
    return df

    print("🧹 Normalizando nombres...")
    df[col_name] = df[col_name].map(normalize_text)

    print("✂️ Simplificando a nombre + apellido...")
    df[col_name] = df[col_name].map(extract_first_name_and_surname)

    unique_names = list(set(filter(None, df[col_name])))

    print(f"🔍 Detectando duplicados fuzzy (threshold={threshold})...")

    canonical_map = {}

    for name in unique_names:
        if name in canonical_map:
            continue

        matches = process.extract(name, unique_names, limit=10)

        for match_name, score in matches:
            if score >= threshold:
                canonical_map[match_name] = name

    df[col_name] = df[col_name].map(lambda x: canonical_map.get(x, x))

    print("✅ Limpieza de cobrador completada")

    return df
