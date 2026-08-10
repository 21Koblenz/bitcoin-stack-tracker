from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "custom_components/bitcoin_stack_tracker/frontend/static/app.js").read_text(encoding="utf-8")
DE = (ROOT / "custom_components/bitcoin_stack_tracker/translations/de.json").read_text(encoding="utf-8")


def test_performance_separates_profit_loss_types():
    assert 'bookProfitLossPerformance:"Buchgewinn/-verlust"' in APP
    assert 'realizedProfitLossPerformance:"Realisierter Gewinn/Verlust"' in APP
    assert 'profitLossPerformance:"Gesamtgewinn/-verlust"' in APP
    assert 'chart.realized_profit_loss?.[currency]' in APP
    assert 'function currentProfitMetrics(currency)' in APP
    assert 'profit.unrealized/profit.invested*100' in APP
    assert 'profit.realized/profit.lifetimeCapital*100' not in APP
    assert 'cumulativePurchaseOutlay' in APP


def test_portfolio_explanation_is_explicit():
    assert 'Portfoliowert wird cashflow-bereinigt' in APP
    assert 'Buchgewinn/-verlust bezieht sich auf den offenen Einstand' in APP


def test_home_assistant_unrealized_sensor_uses_book_label():
    assert 'Buchgewinn/-verlust {currency}' in DE
    assert 'Unrealisierter Gewinn/Verlust {currency}' not in DE


def test_fifo_sale_gain_is_labeled_realized():
    assert 'gain:"Realisierter Gewinn/Verlust"' in APP
