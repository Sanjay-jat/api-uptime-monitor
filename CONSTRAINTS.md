# Constraints

Last reviewed: 2026-10-04

## Floor (hamesha lagu, koi setup nahi)

- No new suppression comments: `# noqa`, `# type: ignore`
- No skipped tests: `@pytest.mark.skip`, `xfail`, ya test delete, bina commit message mein wajah ke
- No stubs: `raise NotImplementedError`, khali `except:`, `pass` jahan code hona chahiye
- No secrets in source. `.env` kabhi commit nahi hoti, sirf `.env.example`
- Ye file kisi change ko pass karwane ke liye kamzor nahi ki jayegi

## Enforced with numbers

| Dimension | Rule | Checked by | Runs at |
|-----------|------|-----------|---------|
| Lint | Zero errors | `ruff check .` | har edit, CI |
| Format | Zero diff | `ruff format --check .` | CI |
| Tests | Sab pass | `pytest` | har task ke end, CI |
| Coverage (project) | >= 90%, girna nahi chahiye | `pytest --cov=app` | CI |

Reason: 80% itna hai ki naye code par test likhna padega, aur itna kam ki ek config line na rok de. Project coverage ratchet hai: aaj ka number hold karo, badhe to update karo.

## Planned (tool abhi installed nahi, T14 mein CI ke saath)

- Dependency vulnerabilities: nothing at high or above (`pip-audit`)
- Coverage on changed lines >= 80% (`diff-cover`, CI mein)

## Project rules

- Dusre user ka data hamesha 404, kabhi 403 nahi
- Har fix hua bug `tests/regression/test_regressions.py` mein ek test paata hai
- README mein performance number tabhi jab naapa ho
- Sirf maange gaye badlav. Current task ke bahar ki files ko haath nahi

## Exceptions

Abhi koi nahi. Har exception ka owner aur expiry date hona chahiye.
