# Sample notes export

`notes-sample.json` is a small, made-up notes export in the same format as the real one.
Use it to try **Admin › Import Apple Notes** on your PC after loading the demo data (`python manage.py demo`).

Every note in it is made up. It has ten notes, one of each kind the import has to handle:

| Note | What the import does with it |
| --- | --- |
| Otis Fenwick (2022), with an address and a phone | Proposes a new account |
| Otis Fenwick (2024), same phone | Joins the account made from the first note |
| Sra. Camila Restrepo, with an address | Proposes a new account |
| Terrence Oakes, with a phone | Finds the demo customer by phone |
| Denise Wyckoff, "2309 Grove Avenue" | Finds the demo customer by address ("Avenue" matches "Ave") |
| Material para el lunes | No customer found |
| Cumpleaños de la abuela | Looks personal |
| Correo viejo (a made-up email and password) | Set aside: counted, never stored |
| Cuenta del banco, in the "Passwords and accounts" folder | Set aside: counted, never stored |
| An empty note | Counted as empty |

Never put the real notes export in this folder or anywhere in the repository: it holds real customers and passwords.
