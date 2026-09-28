"""Le nom d'un pays à partir de son code ISO à deux lettres, dans la langue de l'écran.

Une facture porte un code pays ; le sell-out au jour nomme le marché derrière ce code, et
c'est ce nom que l'annuaire range dans un périmètre. Un pays facturé qui n'a pas de
sell-out — un distributeur à l'export, un marché sans magasin — n'avait donc pas de nom,
et tombait « sans périmètre » quoi que dise l'annuaire. Cette table donne le nom ; l'annuaire
seul décide du périmètre, et un pays qu'il ne nomme pas reste non rangé, dit comme tel.
Une taxonomie, pas une donnée : les codes et les noms sont ceux de la norme, écrits dans
l'orthographe que le cockpit utilise déjà pour ses marchés.
"""

from __future__ import annotations

from typing import Dict

ISO_NAMES: Dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan", "AG": "Antigua and Barbuda",
    "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AR": "Argentina", "AT": "Austria",
    "AU": "Australia", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain",
    "BI": "Burundi", "BJ": "Benin", "BN": "Brunei", "BO": "Bolivia", "BR": "Brazil", "BS": "Bahamas",
    "BT": "Bhutan", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize", "CA": "Canada",
    "CD": "Congo (Kinshasa)", "CF": "Central African Republic", "CG": "Congo (Brazzaville)",
    "CH": "Switzerland", "CI": "Ivory Coast", "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "CV": "Cape Verde", "CY": "Cyprus",
    "CZ": "Czech Republic", "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt",
    "ER": "Eritrea", "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FR": "France",
    "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia", "GH": "Ghana",
    "GI": "Gibraltar", "GM": "Gambia", "GN": "Guinea", "GQ": "Equatorial Guinea", "GR": "Greece",
    "GT": "Guatemala", "GU": "Guam", "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HN": "Honduras", "HR": "Croatia", "HT": "Haiti", "HU": "Hungary", "ID": "Indonesia",
    "IE": "Ireland", "IL": "Israel", "IN": "India", "IQ": "Iraq", "IR": "Iran", "IS": "Iceland",
    "IT": "Italy", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan",
    "KH": "Cambodia", "KR": "Korea", "KW": "Kuwait", "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon",
    "LC": "Saint Lucia", "LI": "Liechtenstein", "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro", "MG": "Madagascar", "MK": "North Macedonia",
    "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia", "MO": "Macau", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NE": "Niger", "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands",
    "NO": "Norway", "NP": "Nepal", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PR": "Puerto Rico", "PT": "Portugal", "PY": "Paraguay", "QA": "Qatar",
    "RE": "Reunion", "RO": "Romania", "RS": "Serbia", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SI": "Slovenia", "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino", "SN": "Senegal",
    "SR": "Suriname", "SV": "El Salvador", "SY": "Syria", "SZ": "Eswatini", "TD": "Chad",
    "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan", "TM": "Turkmenistan", "TN": "Tunisia",
    "TR": "Turkey", "TT": "Trinidad and Tobago", "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine",
    "UG": "Uganda", "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan", "VE": "Venezuela",
    "VN": "Vietnam", "XK": "Kosovo", "YE": "Yemen", "ZA": "South Africa", "ZM": "Zambia",
    "ZW": "Zimbabwe",
}


def country_name(iso2: str) -> str:
    """Le nom du pays, ou le code tel quel quand la norme ne le connaît pas."""
    code = (iso2 or "").strip().upper()
    return ISO_NAMES.get(code, code)
