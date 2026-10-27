"""Section 3: export the two funnel marts and their headline metrics."""
from src import config


def main(con):
    fulfil = con.execute("select * from mart_fulfilment_funnel").df()
    seller = con.execute("select * from mart_seller_funnel").df()
    fulfil.to_csv(config.OUTPUTS / "funnel_fulfilment.csv", index=False)
    seller.to_csv(config.OUTPUTS / "funnel_seller.csv", index=False)

    f = fulfil[fulfil.dimension == "overall"].iloc[0]
    s = seller[seller.dimension == "overall"].iloc[0]
    # Seller sales that predate the closed deal: a data quality flag.
    pre_deal = con.execute("""
        select count(*) from stg_closed_deals d
        join (select seller_id, min(purchase_date) first_sale from mart_seller_sales group by 1) a
          using (seller_id)
        where a.first_sale < d.won_at::date""").fetchone()[0]
    return {
        "funnel_orders": int(f.n_purchased),
        "funnel_delivered": int(f.n_delivered),
        "funnel_conv_purchased_to_delivered": float(f.conv_purchased_to_delivered),
        "funnel_conv_delivered_to_reviewed": float(f.conv_delivered_to_reviewed),
        "funnel_conv_purchased_to_approved": float(f.conv_purchased_to_approved),
        "funnel_conv_approved_to_shipped": float(f.conv_approved_to_shipped),
        "funnel_conv_shipped_to_delivered": float(f.conv_shipped_to_delivered),
        "funnel_median_h_purchase_to_approve": float(f.median_h_purchase_to_approve),
        "funnel_median_h_approve_to_ship": float(f.median_h_approve_to_ship),
        "funnel_median_h_ship_to_deliver": float(f.median_h_ship_to_deliver),
        "seller_leads": int(s.n_leads),
        "seller_closed": int(s.n_closed),
        "seller_first_sale": int(s.n_first_sale),
        "seller_first_sale_observed": int(s.n_first_sale_observed),
        "seller_censored": int(s.n_censored),
        "seller_still_selling": int(s.n_still_selling),
        "seller_conv_lead_to_closed": float(s.conv_lead_to_closed),
        "seller_conv_closed_to_first_sale": float(s.conv_closed_to_first_sale),
        "seller_conv_first_sale_to_still_selling": float(s.conv_first_sale_to_still_selling),
        "seller_first_sale_before_deal": int(pre_deal),
    }
