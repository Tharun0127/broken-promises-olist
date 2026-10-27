"""Renders README.md and docs/memo.md from templates, filling every number from metrics.json.

Template syntax: {{key}} or {{key|format}}. Formats:
    pct   -> 12.3%      (value is a share)
    pct0  -> 12%
    pp    -> +1.2 pp    (value is a difference of shares)
    int   -> 12,345
    num1  -> 12.3
    num2  -> 1.23
    brl   -> R$ 12,345
    signed2 -> +0.12
    str   -> as is
"""
import re

from src import config

FORMATS = {
    "pct": lambda v: f"{100 * v:.1f}%",
    "pct0": lambda v: f"{100 * v:.0f}%",
    "pp": lambda v: f"{100 * v:+.1f} pp",
    "ppabs": lambda v: f"{100 * abs(v):.1f} pp",
    "int": lambda v: f"{v:,.0f}",
    "num1": lambda v: f"{v:.1f}",
    "num2": lambda v: f"{v:.2f}",
    "signed2": lambda v: f"{v:+.2f}",
    "brl": lambda v: f"R$ {v:,.0f}",
    "str": lambda v: str(v),
}
TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*(?:\|\s*([a-z0-9]+))?\s*\}\}")


def render(template, m):
    def sub(match):
        key, fmt = match.group(1), match.group(2) or "str"
        if key not in m:
            raise KeyError(f"Template uses unknown metric '{key}'")
        return FORMATS[fmt](m[key])
    return TOKEN.sub(sub, template)


def answer_text(m):
    return render(
        "Partly. Late orders get far more 1-star reviews ({{naive_one_star_late|pct}} vs "
        "{{naive_one_star_on_time|pct}} on time), but missing the promise by one day is not the main cause. "
        "Once the trend is allowed for, the jump at the promise date is {{rd_one_star_estimate|pp}} "
        "(95% CI {{rd_one_star_ci_low|pp}} to {{rd_one_star_ci_high|pp}}). The damage builds over the "
        "following days: {{rd_one_star_day1_mean|pct}} 1-star on day 1, {{one_star_day3|pct}} on day 3, the "
        "point where most late customers are surveyed before the parcel arrives. There is no detectable effect "
        "on repeat purchase ({{rd_repeat_180_estimate|pp}}, CI {{rd_repeat_180_ci_low|pp}} to "
        "{{rd_repeat_180_ci_high|pp}}), and repeat purchase is so rare ({{repeat_rate_180d|pct}} within 180 days) "
        "that even the worst case is {{size_loss_high_all_late|brl}} of order value a quarter.", m)


def recommendation_text(m):
    return render(
        "Test a proactive delay message for orders that miss their date, with survey timing held the same in "
        "both arms. It needs {{exp_n_per_arm|int}} late orders per arm, about {{exp_months|num1}} months at "
        "2017 to 2018 volumes. Separately, stop sending the review survey before the parcel arrives.", m)


def render_file(template_path, out_path, m):
    text = render(template_path.read_text(encoding="utf-8"), m)
    out_path.write_text(text, encoding="utf-8")
    return out_path


def main(m):
    m = {**m, "answer": answer_text(m), "recommendation": recommendation_text(m)}
    t = config.DOCS / "templates"
    render_file(t / "README.md.tmpl", config.ROOT / "README.md", m)
    render_file(t / "memo.md.tmpl", config.DOCS / "memo.md", m)
