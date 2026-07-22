from evds import evdsAPI
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime

from forecasting import CURRENCY_SERIES, data_path

load_dotenv()
api_key = os.getenv("TCMB_API_KEY")

evds = evdsAPI(api_key)

# Fetch data in yearly chunks to avoid API range limits
date_ranges = [
    ("01-01-2019", "31-12-2020"),
    ("01-01-2021", "31-12-2022"),
    ("01-01-2023", "31-12-2024"),
    ("01-01-2025", datetime.today().strftime("%d-%m-%Y")),
]

def main():
    series_list = list(CURRENCY_SERIES.values())

    # EVDS tek cagrida birden fazla seriyi kabul ediyor; her doviz icin ayri
    # ayri istek atmak yerine her tarih araligi icin TUM dovizleri tek
    # seferde cekiyoruz (sadece 4 cagri).
    all_data = []
    for start, end in date_ranges:
        chunk = evds.get_data(series_list, startdate=start, enddate=end)
        all_data.append(chunk)
        print(f"Fetched {start} to {end}: {len(chunk)} rows")

    raw = pd.concat(all_data, ignore_index=True)
    raw = raw.rename(columns={"Tarih": "date"})
    raw["date"] = pd.to_datetime(raw["date"], format="%d-%m-%Y")

    for code, series in CURRENCY_SERIES.items():
        print(f"\n=== {code}/TRY ===")

        value_column = series.replace(".", "_")
        df = raw[["date", value_column]].rename(columns={value_column: "rate"})

        # Eksik degerleri ve (araliklar cakisirsa olusabilecek) tekrarlayan
        # tarihleri temizle
        df = df.dropna()
        df = df.drop_duplicates(subset="date")
        df = df.sort_values("date").reset_index(drop=True)

        print(df.head())
        print(df.tail())
        print(f"Total rows after cleaning: {len(df)}")

        out_path = data_path(code)
        df.to_csv(out_path, index=False)
        print(f"Data saved to {out_path}")


if __name__ == "__main__":
    main()
