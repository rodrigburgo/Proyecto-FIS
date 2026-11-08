"""Genera un CSV de prueba con el mismo formato de tu base + 'Estado de la cita' y 'Justificada',
con pacientes que se repiten (para probar RN-02: >=3 inasistencias injustificadas en 6 meses).

Uso:  python generar_datos_prueba.py --filas 300000 --salida datos_prueba.csv
"""
import argparse

import numpy as np
import pandas as pd

ESPECIALIDADES = ["Medicina General", "Urgencias", "Pediatría", "Ginecología", "Psiquiatría",
                  "Dermatología", "Oftalmología", "Ortopedia", "Cardiología", "Neurología"]
PESOS_ESP = [.35, .15, .10, .10, .05, .05, .05, .05, .05, .05]
CIUDADES = ["Bogotá", "Zipaquirá", "Chía", "Soacha", "Cajicá", "Medellín", "Barranquilla", "Cali"]
PESOS_CIU = [.70, .05, .05, .05, .05, .04, .03, .03]
CENTROS = ["Hospital Meissen", "Hospital Kennedy", "Hospital Universitario San Ignacio", "Clínica del Country",
           "Compensar Calle 26", "Centro Médico EPS Sanitas", "Clínica Colombia", "Hospital El Tunal", "Clínica Marly"]
DIAGS = ["Infección respiratoria aguda", "Hipertensión arterial", "Chequeo general", "Ansiedad", "Diabetes mellitus",
         "Trauma leve", "Control de rutina", "Infección urinaria", "Lumbalgia", "Gastroenteritis", "Dolor abdominal", "Fractura"]
MEDS = ["Acetaminofén", "Ibuprofeno", "Ninguno", "Losartán", "Amoxicilina", "Diclofenaco", "Salbutamol", "Metformina"]
SAT = ["1 - Muy Insatisfecho", "2 - Insatisfecho", "3 - Neutral", "4 - Satisfecho", "5 - Muy Satisfecho"]


def main(filas, salida, semilla=7):
    rng = np.random.default_rng(semilla)
    n_pac = int(filas / 2.2)
    docs = rng.integers(10_000_000, 1_999_999_999, n_pac)
    edad_pac = rng.integers(1, 95, n_pac)
    sexo_pac = rng.choice(["Femenino", "Masculino", "Otro"], n_pac, p=[.51, .48, .01])
    prob_falta = np.where(rng.random(n_pac) < 0.07, 0.65, 0.12)  # 7% de pacientes faltan mucho
    idx = rng.choice(n_pac, filas, p=rng.dirichlet(np.ones(n_pac) * 2))
    ini = pd.Timestamp("2025-10-01")
    fechas = ini + pd.to_timedelta(rng.integers(0, 365 * 24 * 60, filas), unit="m")
    falto = rng.random(filas) < prob_falta[idx]
    df = pd.DataFrame({
        "Tipo Documento": rng.choice(["CC", "TI", "CE", "Pasaporte"], filas, p=[.85, .10, .03, .02]),
        "Documento": docs[idx], "Edad": edad_pac[idx],
        "Ciudad": rng.choice(CIUDADES, filas, p=PESOS_CIU), "Centro Atención": rng.choice(CENTROS, filas),
        "Especialidad": rng.choice(ESPECIALIDADES, filas, p=PESOS_ESP),
        "Remitido a otra especialidad": rng.choice(["Sí", "No"], filas, p=[.25, .75]),
        "Ha venido antes": rng.choice(["Sí", "No"], filas, p=[.65, .35]),
        "Diagnóstico": rng.choice(DIAGS, filas), "Sexo": sexo_pac[idx],
        "Nivel de Triage": rng.choice(["I", "II", "III", "IV", "V"], filas, p=[.05, .15, .40, .30, .10]),
        "Estado del Paciente": rng.choice(["Estable", "Alta médica", "Observación", "Remitido a hospitalización", "Crítico"], filas, p=[.4, .3, .2, .05, .05]),
        "Medicamento Recetado": rng.choice(MEDS, filas),
        "Nivel de Satisfacción": rng.choice(SAT, filas, p=[.05, .10, .20, .40, .25]),
        "Fecha de Ingreso": fechas.strftime("%Y-%m-%d %H:%M"),
        "Estado de la cita": np.where(falto, "Faltó", "Asistió"),
        "Justificada": np.where(falto & (rng.random(filas) < 0.2), "Sí", "No"),
    }).sort_values("Fecha de Ingreso")
    df.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"{len(df):,} filas -> {salida}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--filas", type=int, default=100_000)
    ap.add_argument("--salida", default="datos_prueba.csv")
    a = ap.parse_args()
    main(a.filas, a.salida)
