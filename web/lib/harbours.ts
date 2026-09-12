/**
 * Indian fishing harbours / landing centres — bundled into the JS bundle
 * so the SOS panel works 100 percent OFFLINE (no fetch, no network).
 * Positions: harbour-town coastal references from public charts,
 * approximate to ~0.5 NM; every one sanity-checked against the real
 * GLOBE 1 km land mask (generator steps in git history). Guidance only.
 */
export type Harbour = { name: string; lat: number; lon: number };
export const HARBOURS: Harbour[] = [
  {
    "name": "Jakhau (Kutch)",
    "lat": 23.222,
    "lon": 68.612
  },
  {
    "name": "Mundra",
    "lat": 22.737,
    "lon": 69.712
  },
  {
    "name": "Mandvi",
    "lat": 22.833,
    "lon": 69.353
  },
  {
    "name": "Okha/Dwarka",
    "lat": 22.468,
    "lon": 69.073
  },
  {
    "name": "Porbandar",
    "lat": 21.64,
    "lon": 69.624
  },
  {
    "name": "Madhavad (Mangrol)",
    "lat": 21.117,
    "lon": 70.115
  },
  {
    "name": "Veraval",
    "lat": 20.91,
    "lon": 70.365
  },
  {
    "name": "Jafarabad",
    "lat": 20.867,
    "lon": 71.376
  },
  {
    "name": "Pipavav",
    "lat": 20.925,
    "lon": 71.504
  },
  {
    "name": "Diu",
    "lat": 20.715,
    "lon": 70.985
  },
  {
    "name": "Sachin/Hazira (Surat)",
    "lat": 21.09,
    "lon": 72.63
  },
  {
    "name": "Daman",
    "lat": 20.422,
    "lon": 72.836
  },
  {
    "name": "Satpati/Arnala (Palghar)",
    "lat": 19.4508,
    "lon": 72.7339
  },
  {
    "name": "Vasai Killa Bunder",
    "lat": 19.37,
    "lon": 72.8
  },
  {
    "name": "Sassoon Dock (Mumbai)",
    "lat": 18.95,
    "lon": 72.83
  },
  {
    "name": "Mora-Karave (Uran)",
    "lat": 18.88,
    "lon": 72.95
  },
  {
    "name": "Alibag",
    "lat": 18.642,
    "lon": 72.872
  },
  {
    "name": "Murud-Janjira",
    "lat": 18.327,
    "lon": 72.965
  },
  {
    "name": "Shrivardhan",
    "lat": 18.033,
    "lon": 73.024
  },
  {
    "name": "Dabhol",
    "lat": 17.585,
    "lon": 73.16
  },
  {
    "name": "Harne",
    "lat": 17.6881,
    "lon": 73.1205
  },
  {
    "name": "Mirya/Ratnagiri",
    "lat": 16.983,
    "lon": 73.292
  },
  {
    "name": "Jaigad",
    "lat": 17.3038,
    "lon": 73.2242
  },
  {
    "name": "Devgad",
    "lat": 16.376,
    "lon": 73.383
  },
  {
    "name": "Malvan",
    "lat": 16.055,
    "lon": 73.466
  },
  {
    "name": "Vengurla",
    "lat": 15.857,
    "lon": 73.63
  },
  {
    "name": "Chapora (Goa)",
    "lat": 15.607,
    "lon": 73.742
  },
  {
    "name": "Betim/Panaji",
    "lat": 15.502,
    "lon": 73.83
  },
  {
    "name": "Mormugao/Vasco",
    "lat": 15.4069,
    "lon": 73.8131
  },
  {
    "name": "Cutbona (S. Goa)",
    "lat": 15.22,
    "lon": 73.975
  },
  {
    "name": "Karwar",
    "lat": 14.813,
    "lon": 74.117
  },
  {
    "name": "Tadri/Kumta",
    "lat": 14.43,
    "lon": 74.39
  },
  {
    "name": "Honnavar",
    "lat": 14.28,
    "lon": 74.437
  },
  {
    "name": "Bhatkal",
    "lat": 13.983,
    "lon": 74.552
  },
  {
    "name": "Gangolli (Kundapur)",
    "lat": 13.6539,
    "lon": 74.6586
  },
  {
    "name": "Malpe (Udupi)",
    "lat": 13.352,
    "lon": 74.697
  },
  {
    "name": "Mangalore Bunder",
    "lat": 12.845,
    "lon": 74.842
  },
  {
    "name": "Kasaragod",
    "lat": 12.5,
    "lon": 74.987
  },
  {
    "name": "Azhikkal (Kannur)",
    "lat": 11.933,
    "lon": 75.339
  },
  {
    "name": "Thalassery",
    "lat": 11.74,
    "lon": 75.494
  },
  {
    "name": "Beypore (Kozhikode)",
    "lat": 11.1776,
    "lon": 75.7919
  },
  {
    "name": "Ponnani",
    "lat": 10.7801,
    "lon": 75.9251
  },
  {
    "name": "Munambam (Ernakulam)",
    "lat": 10.177,
    "lon": 76.204
  },
  {
    "name": "Fort Kochi",
    "lat": 9.966,
    "lon": 76.242
  },
  {
    "name": "Sakthikulangara (Kollam)",
    "lat": 8.954,
    "lon": 76.537
  },
  {
    "name": "Vizhinjam (TVM)",
    "lat": 8.383,
    "lon": 76.992
  },
  {
    "name": "Muttom (Kanyakumari W)",
    "lat": 8.122,
    "lon": 77.321
  },
  {
    "name": "Colachel",
    "lat": 8.183,
    "lon": 77.256
  },
  {
    "name": "Kanyakumari",
    "lat": 8.087,
    "lon": 77.547
  },
  {
    "name": "Thoothukudi (Tuticorin)",
    "lat": 8.76,
    "lon": 78.2082
  },
  {
    "name": "Pamban (Rameswaram)",
    "lat": 9.283,
    "lon": 79.31
  },
  {
    "name": "Mandapam",
    "lat": 9.278,
    "lon": 79.13
  },
  {
    "name": "Nagapattinam",
    "lat": 10.763,
    "lon": 79.845
  },
  {
    "name": "Karaikal",
    "lat": 10.915,
    "lon": 79.838
  },
  {
    "name": "Cuddalore",
    "lat": 11.715,
    "lon": 79.772
  },
  {
    "name": "Puducherry",
    "lat": 11.9282,
    "lon": 79.8332
  },
  {
    "name": "Chennai",
    "lat": 13.1,
    "lon": 80.294
  },
  {
    "name": "Machilipatnam",
    "lat": 16.17,
    "lon": 81.14
  },
  {
    "name": "Nizampatnam",
    "lat": 15.917,
    "lon": 80.673
  },
  {
    "name": "Kakinada",
    "lat": 16.972,
    "lon": 82.255
  },
  {
    "name": "Visakhapatnam",
    "lat": 17.685,
    "lon": 83.262
  },
  {
    "name": "Bheemunipatnam",
    "lat": 17.893,
    "lon": 83.447
  },
  {
    "name": "Kalingapatnam (Srikakulam)",
    "lat": 18.333,
    "lon": 84.125
  },
  {
    "name": "Gopalpur (Odisha)",
    "lat": 19.262,
    "lon": 84.902
  },
  {
    "name": "Paradeep",
    "lat": 20.262,
    "lon": 86.615
  },
  {
    "name": "Dhamra",
    "lat": 20.7913,
    "lon": 86.9749
  },
  {
    "name": "Astaranga/Puri side",
    "lat": 19.967,
    "lon": 86.398
  },
  {
    "name": "Digha Mohana (WB)",
    "lat": 21.623,
    "lon": 87.503
  },
  {
    "name": "Shankarpur (WB)",
    "lat": 21.653,
    "lon": 87.558
  },
  {
    "name": "Haldia",
    "lat": 22.03,
    "lon": 88.069
  },
  {
    "name": "Diamond Harbour (WB)",
    "lat": 22.193,
    "lon": 88.195
  }
];
