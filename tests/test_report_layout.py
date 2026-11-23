from app import app


def test_report_message_is_directly_below_category_filter():
    with app.test_client() as client:
        page = client.get('/').get_data(as_text=True)

    filter_position = page.index('id="report-domain"')
    message_position = page.index('id="report-message"')
    chart_position = page.index('id="report-chart"')
    assert filter_position < message_position < chart_position
