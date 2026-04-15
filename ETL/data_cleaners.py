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
    num_words = len(words)

    if num_words == 0:
        return None
    elif num_words == 1:
        return words[0]
    elif num_words == 2:
        return f"{words[0]} {words[1]}"
    else:
        # Para más de dos palabras, primer nombre y penúltimo (primer apellido)
        return f"{words[0]} {words[num_words - 2]}"


def apply_fuzzy_matching_to_cobrador(
    df: pd.DataFrame, threshold: int = 85
) -> pd.DataFrame:
    col_name = "COBRADOR"
    if col_name not in df.columns:
        print(f"Advertencia: La columna '{col_name}' no se encontró en el DataFrame.")
        return df

    print(f"Aplicando limpieza y fuzzy matching a la columna '{col_name}'...")

    df["_normalized_cobrador"] = df[col_name].apply(normalize_text)

    unique_names = df["_normalized_cobrador"].dropna().unique()
    canonical_map = {}

    for name in unique_names:
        if name in canonical_map:
            continue
        # Fuzzing sobre el nombre completo normalizado
        matches = [
            n for n in unique_names if fuzz.token_set_ratio(name, n) >= threshold
        ]

        # Elegimos el canónico (nombre completo normalizado) del grupo
        # Podríamos elegir el más corto, o el que aparece primero alfabéticamente
        canonical_full_name = sorted(matches)[0]

        # El mapa almacena el nombre canónico COMPLETO normalizado
        for m in matches:
            canonical_map[m] = canonical_full_name

    # Aplicamos el mapeo al nombre COMPLETO normalizado
    df[col_name] = (
        df["_normalized_cobrador"]
        .map(canonical_map)
        .fillna(df[col_name])  # Fallback al original si no hay match
        .apply(extract_first_name_and_surname)  # <- Recorte FINAL a Nombre + Apellido
    )

    df = df.drop(columns=["_normalized_cobrador"])

    print(f"Limpieza de la columna '{col_name}' completada.")
    return df
