import sqlite3
import pandas as pd

def analyze_performance():
    conn = sqlite3.connect('trades.db')
    try:
        # 1. Last 10 trades with outcomes
        query = """
            SELECT 
                t.id, 
                t.market_question, 
                t.side, 
                t.market_price, 
                t.edge, 
                t.materiality,
                t.total_latency_ms,
                o.result,
                t.created_at
            FROM trades t
            LEFT JOIN outcomes o ON t.id = o.trade_id
            ORDER BY t.created_at DESC
            LIMIT 10
        """
        df = pd.read_sql_query(query, conn)
        print("\n=== RECENT TRADES ===")
        print(df)

        # 2. Accuracy Stats
        accuracy_query = """
            SELECT 
                o.result,
                COUNT(*) as count
            FROM trades t
            JOIN outcomes o ON t.id = o.trade_id
            GROUP BY o.result
        """
        acc_df = pd.read_sql_query(accuracy_query, conn)
        print("\n=== ACCURACY STATS ===")
        print(acc_df)
        
        # Calculate Win Rate
        wins = acc_df[acc_df['result'] == 'WON']['count'].sum()
        total = acc_df['count'].sum()
        if total > 0:
            print(f"Win Rate: {(wins/total)*100:.2f}% ({wins}/{total})")
        else:
            print("No resolved trades found.")

        # 3. Latency Analysis
        latency_query = """
            SELECT 
                AVG(classification_latency_ms) as avg_class_latency,
                AVG(total_latency_ms) as avg_total_latency,
                MAX(total_latency_ms) as max_total_latency
            FROM trades
        """
        lat_df = pd.read_sql_query(latency_query, conn)
        print("\n=== LATENCY ANALYSIS (ms) ===")
        print(lat_df)

        # 4. Mixed Mode Breakdown
        # Check if we have different models in 'classification' or 'signals'
        # Actually let's just look at 'signals' column
        # query_signals = "SELECT signals FROM trades WHERE signals IS NOT NULL LIMIT 5"
        # signals_df = pd.read_sql_query(query_signals, conn)
        # print("\n=== SIGNALS SAMPLE ===")
        # print(signals_df)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    analyze_performance()
