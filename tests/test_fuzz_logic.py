import sys
import os
from pathlib import Path
import pandas as pd
from thefuzz import fuzz

# Añadir la raíz del proyecto al sys.path para poder importar ETL.data_cleaners
root_path = Path(__file__).resolve().parents[1]
sys.path.append(str(root_path))

from ETL.data_cleaners import normalize_text, extract_first_name_and_surname


def logic_current(df, threshold=85):
    """Lógica actual: Recortar -> Fuzzing -> Canónico"""
    df = df.copy()
    df["_normalized"] = df["COBRADOR"].apply(normalize_text)
    df["_fuzzy_key"] = df["_normalized"].apply(extract_first_name_and_surname)

    unique_keys = df["_fuzzy_key"].dropna().unique()
    canonical_map = {}

    for key in unique_keys:
        if key in canonical_map:
            continue
        matches = [k for k in unique_keys if fuzz.token_set_ratio(key, k) >= threshold]
        candidates = (
            df[df["_fuzzy_key"].isin(matches)]["COBRADOR"].dropna().unique().tolist()
        )
        candidates.sort()
        canonical = (
            candidates[0] if candidates else key
        )  # Aquí se elige el canónico del original
        for m in matches:
            canonical_map[m] = canonical

    df["RESULTADO_ACTUAL"] = (
        df["_fuzzy_key"]
        .map(canonical_map)
        .apply(normalize_text)
        .apply(extract_first_name_and_surname)
    )
    return df["RESULTADO_ACTUAL"]


def logic_proposed(df, threshold=85):
    """Lógica propuesta: Fuzzing (completo) -> Canónico (nombre completo) -> Recortar (final)"""
    df = df.copy()
    df["_normalized"] = df["COBRADOR"].apply(normalize_text)

    unique_names = df["_normalized"].dropna().unique()
    canonical_map = {}

    for name in unique_names:
        if name in canonical_map:
            continue
        matches = [
            n for n in unique_names if fuzz.token_set_ratio(name, n) >= threshold
        ]

        # Elegimos el canónico entre los nombres completos normalizados (el primero alfabético)
        canonical_full_name = sorted(matches)[0]

        # APLICAMOS extract_first_name_and_surname AL CANÓNICO ELEGIDO PARA EL MAPA
        final_canonical_short = extract_first_name_and_surname(canonical_full_name)

        for m in matches:
            # El mapa ahora guarda directamente el formato deseado (nombre + apellido)
            canonical_map[m] = final_canonical_short

    # El recorte ya no es necesario aquí, ya que el mapa ya contiene los valores recortados
    df["RESULTADO_PROPUESTO"] = df["_normalized"].map(canonical_map)
    return df["RESULTADO_PROPUESTO"]


def run_test():
    test_cases = [
        "JOSE ANTONIO PEREZ",
        "JOSE ANT PEREZ",
        "JOSE PEREZ",
        "JUAN RODRIGUEZ",
        "JUAN RODRIGEZ",
        "MARIA DE LOS ANGELES RUIZ",
        "MARIA ANGELES RUIZ",
        "CARLOS MARIN G.",
        "CARLOS MARIN GALVEZ",
    ]

    df = pd.DataFrame({"COBRADOR": test_cases})

    # Ejecutar ambas lógicas
    df["ACTUAL (Recorte primero)"] = logic_current(df)
    df["PROPUESTA (Fuzz primero)"] = logic_proposed(df)

    print("\n--- COMPARATIVA DE LÓGICAS DE FUZZING ---")
    print(df.to_string(index=False))
    print("\n------------------------------------------")


if __name__ == "__main__":
    run_test()
