from app import app


def render_home_as(role=None):
    with app.test_client() as client:
        if role:
            with client.session_transaction() as session:
                session['user'] = {
                    'id': 1,
                    'username': role,
                    'full_name': 'Pengguna Uji',
                    'role': role,
                }
        return client.get('/').get_data(as_text=True)


def test_guest_does_not_see_add_data_controls():
    page = render_home_as()

    assert 'data-page="add-data"' not in page
    assert 'data-page-target="add-data"' not in page


def test_business_user_can_open_add_data_page():
    page = render_home_as('user')

    assert 'data-page="add-data"' in page
    assert 'data-page-target="add-data"' in page
    assert 'Ajukan data produksi' in page
    assert 'Pengguna Usaha' in page


def test_admins_can_open_add_data_page():
    for role in ('admin_pertanian', 'admin_perikanan'):
        page = render_home_as(role)

        assert 'data-page="add-data"' in page
        assert 'data-page-target="add-data"' in page
