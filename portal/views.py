from flask import (abort, flash, redirect, render_template, request,
                   session, url_for)
import requests, traceback, json, time

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from portal import app
from portal.decorators import authenticated
from portal.utils import (load_portal_client, get_portal_tokens,
                          get_safe_redirect)

# Use these four lines on container
import sys
sys.path.insert(0, '/etc/ci-connect/secrets')

try:
    f = open("/etc/ci-connect/secrets/ciconnect_api_token.txt", "r")
    g = open("/etc/ci-connect/secrets/ciconnect_api_endpoint.txt", "r")
except:
    # Use these two lines below on local
    f = open("/Users/JeremyVan/Documents/Programming/UChicago/CI_Connect/secrets/ciconnect_api_token.txt", "r")
    g = open("/Users/JeremyVan/Documents/Programming/UChicago/CI_Connect/secrets/ciconnect_api_endpoint.txt", "r")

ciconnect_api_token = f.read().split()[0]
ciconnect_api_endpoint = g.read().split()[0]

# Create a custom error handler for Exceptions
@app.errorhandler(Exception)
def exception_occurred(e):
    trace = traceback.format_tb(sys.exc_info()[2])
    app.logger.error("{0} Traceback occurred:\n".format(time.ctime()) +
                     "{0}\nTraceback completed".format("n".join(trace)))
    trace = "<br>".join(trace)
    trace.replace('\n', '<br>')
    return render_template('error.html', exception=trace,
                           debug=app.config['DEBUG'])

@app.route('/error', methods=['GET'])
def errorpage():
    if request.method == 'GET':
        return render_template('error.html')


@app.errorhandler(404)
def not_found(e):
  return render_template("404.html")


@app.route('/', methods=['GET'])
def home():
    """Home page - play with it if you must!"""
    return render_template('home.html')


@app.route('/groups', methods=['GET'])
def groups():
    """OSG Connect groups"""
    if request.method == 'GET':
        query = {'token': ciconnect_api_token}
        groups = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups', params=query)
        groups = groups.json()['groups']
        return render_template('groups.html', groups=groups)


@app.route('/groups/new', methods=['GET', 'POST'])
@authenticated
def create_group():
    """Create groups"""
    query = {'token': session['access_token']}
    if request.method == 'GET':
        sciences = requests.get(ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        return render_template('groups_create.html', sciences=sciences)
    elif request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        field_of_science = request.form['field_of_science']
        description = request.form['description']

        put_group = {"apiVersion": 'v1alpha1', "kind": "Group",
                        'metadata': {'name': name,
                                    'field_of_science': field_of_science,
                                    'email': email, 'phone': phone,
                                    'description': description}}
        create_group = requests.put(ciconnect_api_endpoint + '/v1alpha1/groups/root/subgroups/' + name, params=query, json=put_group)
        print(create_group.url)
        print("CREATED group: {}".format(create_group.content))
        return redirect(url_for('groups'))


@app.route('/groups/<group_name>', methods=['GET', 'POST'])
@authenticated
def view_group(group_name):
    """Detailed view of specific groups"""
    query = {'token': session['access_token']}
    if request.method == 'GET':
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=query)
        group = group.json()['metadata']
        # Remove 'root' and join group naming
        group_name = group['name'].split('.')[1:]
        group_name = '-'.join(group_name)

        return render_template('group_profile.html', group=group, group_name=group_name)


@app.route('/groups/<group_name>/members', methods=['GET', 'POST'])
@authenticated
def view_group_members(group_name):
    """Detailed view of group's members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        print(group_name)
        group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
        memberships = group_members.json()['memberships']
        members = []
        for user in memberships:
            user_id = user['id']
            user_info = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + user_id, params=query)
            user_info = user_info.json()['metadata']
            members.append(user_info)

        return render_template('group_profile_members.html', group_members=members, group_name=group_name)


@app.route('/signup', methods=['GET'])
def signup():
    """Send the user to Globus Auth with signup=1."""
    return redirect(url_for('authcallback', signup=1))


@app.route('/login', methods=['GET'])
def login():
    """Send the user to Globus Auth."""
    return redirect(url_for('authcallback'))


@app.route('/logout', methods=['GET'])
@authenticated
def logout():
    """
    - Revoke the tokens with Globus Auth.
    - Destroy the session state.
    - Redirect the user to the Globus Auth logout page.
    """
    client = load_portal_client()

    # Revoke the tokens with Globus Auth
    for token, token_type in (
            (token_info[ty], ty)
            # get all of the token info dicts
            for token_info in session['tokens'].values()
            # cross product with the set of token types
            for ty in ('access_token', 'refresh_token')
            # only where the relevant token is actually present
            if token_info[ty] is not None):
        client.oauth2_revoke_token(
            token, additional_params={'token_type_hint': token_type})

    # Destroy the session state
    session.clear()

    redirect_uri = url_for('home', _external=True)

    ga_logout_url = []
    ga_logout_url.append(app.config['GLOBUS_AUTH_LOGOUT_URI'])
    ga_logout_url.append('?client={}'.format(app.config['PORTAL_CLIENT_ID']))
    ga_logout_url.append('&redirect_uri={}'.format(redirect_uri))
    ga_logout_url.append('&redirect_name=Globus Sample Data Portal')

    # Redirect the user to the Globus Auth logout page
    return redirect(''.join(ga_logout_url))


@app.route('/profile/new', methods=['GET', 'POST'])
@authenticated
def create_profile():
    identity_id = session.get('primary_identity')
    institution = session.get('institution')
    globus_id = identity_id
    query = {'token': ciconnect_api_token,
             'globus_id': globus_id}

    if request.method == 'GET':
        return render_template('profile_create.html')

    elif request.method == 'POST':
        name = request.form['name']
        unix_name = request.form['unix_name']
        email = request.form['email']
        phone = request.form['phone-number']
        institution = request.form['institution']
        public_key = request.form['sshpubstring']
        globus_id = session['primary_identity']

        superuser = False
        service_account = False
        # Schema and query for adding users to CI Connect DB
        post_user = {"apiVersion": 'v1alpha1',
                    'metadata': {'globusID': globus_id, 'name': name, 'email': email,
                                 'phone': phone, 'institution': institution,
                                 'public_key': public_key,
                                 'unix_name': unix_name, 'superuser': superuser,
                                 'service_account': service_account}}

        r = requests.post(ciconnect_api_endpoint + '/v1alpha1/users', params=query, json=post_user)
        print("Created User: ", r)

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(url_for('profile'))


@app.route('/profile/edit/<user_id>', methods=['GET', 'POST'])
@authenticated
def edit_profile(user_id):
    identity_id = session.get('primary_identity')
    query = {'token': ciconnect_api_token,
             'globus_id': identity_id}
    user = requests.get(
                ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
    user_id = user.json()['metadata']['id']

    if request.method == 'GET':
        # Get user info, pass through as args, convert to json and load input fields
        profile = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/users/' + user_id, params=query)
        profile = profile.json()['metadata']

        return render_template('profile_edit.html', profile=profile)

    elif request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone-number']
        institution = request.form['institution']
        public_key = request.form['sshpubstring']

        globus_id = session['primary_identity']
        superuser = True
        service_account = False
        # Schema and query for adding users to CI Connect DB
        post_user = {"apiVersion": 'v1alpha1',
                    'metadata': {'name': name, 'email': email,
                                 'phone': phone, 'institution': institution,
                                 'public_key': public_key}}
        r = requests.put(ciconnect_api_endpoint + '/v1alpha1/users/' + user_id, params=query, json=post_user)
        print("Updated User: ", r)

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(url_for('profile'))


@app.route('/profile', methods=['GET', 'POST'])
@authenticated
def profile():
    """User profile information. Assocated with a Globus Auth identity."""
    if request.method == 'GET':
        identity_id = session.get('primary_identity')
        profile = None
        query = {'token': ciconnect_api_token,
                 'globus_id': identity_id}

        user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
        user = user.json()
        user_id = user['metadata']['id']
        user_token = user['metadata']['access_token']

        profile = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/users/' + user_id, params=query)
        profile = profile.json()

        if profile:
            profile = profile['metadata']
            name = profile['name']
            email = profile['email']
            phone = profile['phone']
            institution = profile['institution']
            ssh_pubkey = profile['public_key']
        else:
            flash(
                'Please complete any missing profile fields and press Save.', 'warning')

        if request.args.get('next'):
            session['next'] = get_safe_redirect()
        return render_template('profile.html', profile=profile)

    elif request.method == 'POST':
        name = session['name'] = request.form['name']
        email = session['email'] = request.form['email']
        institution = session['institution'] = request.form['institution']
        globus_id = session['primary_identity']
        phone = request.form['phone-number']
        public_key = request.form['sshpubstring']
        superuser = True
        service_account = False

        # flash('Thank you! Your profile has been successfully updated.', 'success')

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(redirect_to)


@app.route('/authcallback', methods=['GET'])
def authcallback():
    """Handles the interaction with Globus Auth."""
    # If we're coming back from Globus Auth in an error state, the error
    # will be in the "error" query string parameter.
    if 'error' in request.args:
        flash("You could not be logged into the portal: " +
              request.args.get('error_description', request.args['error']), 'warning')
        return redirect(url_for('home'))

    # Set up our Globus Auth/OAuth2 state
    redirect_uri = url_for('authcallback', _external=True)

    client = load_portal_client()
    client.oauth2_start_flow(redirect_uri, refresh_tokens=True)

    # If there's no "code" query string parameter, we're in this route
    # starting a Globus Auth login flow.
    if 'code' not in request.args:
        additional_authorize_params = (
            {'signup': 1} if request.args.get('signup') else {})

        auth_uri = client.oauth2_get_authorize_url(
            additional_params=additional_authorize_params)

        return redirect(auth_uri)
    else:
        # If we do have a "code" param, we're coming back from Globus Auth
        # and can start the process of exchanging an auth code for a token.
        code = request.args.get('code')
        tokens = client.oauth2_exchange_code_for_tokens(code)

        id_token = tokens.decode_id_token(client)
        session.update(
            tokens=tokens.by_resource_server,
            is_authenticated=True,
            name=id_token.get('name', ''),
            email=id_token.get('email', ''),
            institution=id_token.get('organization', ''),
            primary_username=id_token.get('preferred_username'),
            primary_identity=id_token.get('sub'),
        )

        # print("URL ROOT CAME FROM: {}".format(request.url_root))
        globus_id = session['primary_identity']
        query = {'token': ciconnect_api_token,
                 'globus_id': globus_id}
        try:
            r = requests.get(
                ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
            print("AUTH: {}".format(r.json()))
            user_info = r.json()
            user_access_token = user_info['metadata']['access_token']
            user_id = user_info['metadata']['id']
            profile = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + user_id, params=query)
            profile = profile.json()
            # print("PROFILE: {}".format(profile))
        except:
            profile = None

        if profile:
            profile = profile['metadata']

            session['name'] = profile['name']
            session['email'] = profile['email']
            session['institution'] = profile['institution']
            session['access_token'] = profile['access_token']
            session['url_root'] = request.url_root
        else:
            session['url_root'] = request.url_root
            return redirect(url_for('create_profile',
                            next=url_for('profile')))

        return redirect(url_for('profile'))
