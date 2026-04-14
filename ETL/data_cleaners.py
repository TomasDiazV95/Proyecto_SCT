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
    if len(words) == 2:
        return f"{words[0]} {words[1]}"
    elif len(words) == 3:
        return f"{words[0]} {words[1]}"
    elif len(words) == 4:
        return f"{words[0]} {words[2]}"
    elif len(words) == 5:
        return f"{words[0]} {words[3]}"
    elif len(words) == 1:
        return words[0]
    return None  # Devolver None si no se puede extraer


def apply_fuzzy_matching_to_cobrador(
    df: pd.DataFrame, threshold: int = 85
) -> pd.DataFrame:
    col_name = "COBRADOR"
    if col_name not in df.columns:
        print(f"Advertencia: La columna '{col_name}' no se encontró en el DataFrame.")
        return df

    print(f"Aplicando limpieza y fuzzy matching a la columna '{col_name}'...")

    df["_normalized_cobrador"] = df[col_name].apply(normalize_text)
    df["_fuzzy_key"] = df["_normalized_cobrador"].apply(extract_first_name_and_surname)

    unique_keys = df["_fuzzy_key"].dropna().unique()
    canonical_map = {}

    for key in unique_keys:
        if key in canonical_map:
            continue
        potential_matches_keys = [
            k for k in unique_keys if fuzz.token_set_ratio(key, k) >= threshold
        ]
        candidates_for_canonical = (
            df[df["_fuzzy_key"].isin(potential_matches_keys)][col_name]
            .dropna()
            .unique()
            .tolist()
        )
        candidates_for_canonical.sort()
        canonical_name = candidates_for_canonical[0] if candidates_for_canonical else key
        for match_key in potential_matches_keys:
            canonical_map[match_key] = canonical_name

    #  Reemplazar COBRADOR con el nombre canónico YA normalizado
    df[col_name] = (
        df["_fuzzy_key"]
        .map(canonical_map)
        .fillna(df[col_name])
        .apply(normalize_text)      # <- normaliza el canónico final
    )

    df = df.drop(columns=["_normalized_cobrador", "_fuzzy_key"])

    print(f"Limpieza de la columna '{col_name}' completada.")
    return df
 
