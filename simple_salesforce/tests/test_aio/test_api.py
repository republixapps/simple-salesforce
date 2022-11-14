# pylint: disable-msg=C0302
# pylint: disable=redefined-outer-name
"""Tests for api.py"""
from collections import OrderedDict
from datetime import datetime
import decimal
import json
from unittest import mock

import aiofiles
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import httpx
import pytest

from simple_salesforce.api import PerAppUsage, Usage
from simple_salesforce.aio.api import (
    build_async_salesforce_client,
    AsyncSalesforce,
    AsyncSFType,
)
from simple_salesforce.exceptions import SalesforceGeneralError
from simple_salesforce.util import date_to_iso8601


DEFAULT_URL = "https://my.salesforce.com/services/data/v52.0/sobjects/{}"
CASE_URL = DEFAULT_URL.format("Case")


# # # # # # # # # # # # # # # # # # # # # #
#
# build_async_salesforce_client (Login/Builder)
#
# # # # # # # # # # # # # # # # # # # # # #
@pytest.mark.asyncio
async def test_build_fail(constants, mock_httpx_client):
    """
    Test the builder function and pass a custom session
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=constants["LOGIN_RESPONSE_SUCCESS"])
    inner(happy_result)
    mock_client.custom_session_attrib = "X-1-2-3"

    with pytest.raises(TypeError):
        await build_async_salesforce_client(
            username="foo@bar.com",
            password="password",
        )


@pytest.mark.asyncio
async def test_build_async_with_session_success(constants, mock_httpx_client):
    """
    Test the builder function and pass a custom session
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=constants["LOGIN_RESPONSE_SUCCESS"])
    inner(happy_result)
    mock_client.custom_session_attrib = "X-1-2-3"

    client = await build_async_salesforce_client(
        username="foo@bar.com",
        password="password",
        security_token="token",
    )
    assert isinstance(client, AsyncSalesforce)
    assert constants["SESSION_ID"] == client.session_id
    assert client.auth_type == "password"

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[0] == "post"
    assert call[1][0].startswith("https://login.salesforce.com/services/Soap/u/")
    assert "SOAPAction" in call[2]["headers"]
    assert call[2]["headers"]["SOAPAction"] == "login"


@pytest.mark.asyncio
async def test_build_async_with_org_id(constants, mock_httpx_client):
    """
    Test the builder function and pass a custom session
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=constants["LOGIN_RESPONSE_SUCCESS"])
    inner(happy_result)
    mock_client.custom_session_attrib = "X-1-2-3"

    client = await build_async_salesforce_client(
        username="foo@bar.com",
        password="password",
        organizationId="super-cool-org",
    )
    assert isinstance(client, AsyncSalesforce)
    assert constants["SESSION_ID"] == client.session_id
    assert client.auth_type == "ipfilter"

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[0] == "post"
    assert call[1][0].startswith("https://login.salesforce.com/services/Soap/u/")
    assert "SOAPAction" in call[2]["headers"]
    assert call[2]["headers"]["SOAPAction"] == "login"


@pytest.mark.asyncio
async def test_build_async_with_direct(constants, mock_httpx_client):
    """
    Test the builder function and pass a custom session
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=constants["LOGIN_RESPONSE_SUCCESS"])
    inner(happy_result)
    mock_client.custom_session_attrib = "X-1-2-3"

    client = await build_async_salesforce_client(
        session_id="X-1-2-3",
        instance_url="https://test.salesforce.com",
    )
    assert isinstance(client, AsyncSalesforce)
    assert "X-1-2-3" == client.session_id
    assert client.auth_type == "direct"
    # Should not have issued an auth call
    assert len(mock_client.method_calls) == 0


@pytest.mark.asyncio
async def test_build_async_with_jwt(constants, mock_httpx_client):
    """
    Test the builder function and pass a custom session
    """
    _, mock_client, inner = mock_httpx_client
    content = {
        "access_token": "this is a token",
        "instance_url": "http://bla"
    }
    happy_result = httpx.Response(200, content=json.dumps(content))
    inner(happy_result)
    mock_client.custom_session_attrib = "jwt-bearer"

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    unencrypted_pem_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    client = await build_async_salesforce_client(
        username="foo@bar.com",
        consumer_key="fake-consumer-key",
        privatekey=unencrypted_pem_private_key
    )
    assert isinstance(client, AsyncSalesforce)
    assert "this is a token" == client.session_id
    assert client.auth_type == "jwt-bearer"

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[0] == "post"
    assert call[1][0].startswith("https://login.salesforce.com/services/oauth2/token")


# # # # # # # # # # # # # # # # # # # # # #
#
# AsyncSFType Tests
#
# # # # # # # # # # # # # # # # # # # # # #


def _create_sf_type(
    object_name="Case", session_id="5", sf_instance="my.salesforce.com"
):
    """Creates AsyncSFType instances"""
    return AsyncSFType(
        object_name=object_name,
        session_id=session_id,
        sf_instance=sf_instance,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_metadata_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for metadata requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.metadata(headers=headers)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_describe_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for describe requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.describe(headers=headers)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/describe"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_describe_layout_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for describe_layout requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.describe_layout(record_id="444", headers=headers)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/describe/layouts/444"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_get_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for get requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = None
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.get(record_id="444", headers=headers)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/444"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_get_customid_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for get_by_custom_id requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.get_by_custom_id(
        custom_id_field="some-field", custom_id="444", headers=headers
    )
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/some-field/444"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_create_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for create requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.create(data={"some": "data"}, headers=headers)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == f"{CASE_URL}/"
    assert call[2]["data"] == '{"some": "data"}'
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "with_headers,with_raw_response",
    ((True, False), (True, True), (False, False), (False, True),),
)
async def test_update_with_request_headers(
    with_headers, with_raw_response, mock_httpx_client
):
    """
    Ensure custom headers are used for update requests
    when passed. Test raw_response kwarg also.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None

    result = await sf_type.update(
        "some-case-id",
        {"some": "data"},
        headers=headers,
        raw_response=with_raw_response,
    )
    if with_raw_response:
        assert result == happy_result
    else:
        assert result == 200
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "PATCH"
    assert call[1][1] == f"{CASE_URL}/some-case-id"
    assert call[2]["data"] == '{"some": "data"}'
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "with_headers,with_raw_response",
    ((True, False), (True, True), (False, False), (False, True),),
)
async def test_upsert_with_request_headers(
    with_headers, with_raw_response, mock_httpx_client
):
    """
    Ensure custom headers are used for upsert requests
    when passed. Test raw_response kwarg also.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None
    result = await sf_type.upsert(
        "some-case-id",
        {"some": "data"},
        headers=headers,
        raw_response=with_raw_response,
    )
    if with_raw_response:
        assert result == happy_result
    else:
        assert result == 200
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "PATCH"
    assert call[1][1] == f"{CASE_URL}/some-case-id"
    assert call[2]["data"] == '{"some": "data"}'
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "with_headers,with_raw_response",
    ((True, False), (True, True), (False, False), (False, True),),
)
async def test_delete_with_request_headers(
    with_headers, with_raw_response, mock_httpx_client
):
    """
    Ensure custom headers are used for delete requests
    when passed. Test raw_response kwarg also.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None
    result = await sf_type.delete(
        "some-case-id", headers=headers, raw_response=with_raw_response
    )
    if with_raw_response:
        assert result == happy_result
    else:
        assert result == 200
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "DELETE"
    assert call[1][1] == f"{CASE_URL}/some-case-id"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_deleted_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for deleted requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    start = datetime.now()
    end = datetime.now()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None
    result = await sf_type.deleted(start, end, headers=headers,)
    start = date_to_iso8601(start)
    end = date_to_iso8601(end)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/deleted/?start={start}&end={end}"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_headers", (True, False))
async def test_updated_with_request_headers(with_headers, mock_httpx_client):
    """
    Ensure custom headers are used for updated requests
    when passed.
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)

    sf_type = _create_sf_type()
    start = datetime.now()
    end = datetime.now()
    headers = {"Sforce-Auto-Assign": "FALSE"} if with_headers else None
    result = await sf_type.updated(start, end, headers=headers,)
    start = date_to_iso8601(start)
    end = date_to_iso8601(end)
    assert result == {}
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{CASE_URL}/updated/?start={start}&end={end}"
    if with_headers:
        assert "Sforce-Auto-Assign" in call[2]["headers"]
        assert call[2]["headers"]["Sforce-Auto-Assign"] == "FALSE"
    else:
        assert "Sforce-Auto-Assign" not in call[2]["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("float_parser", (None, decimal.Decimal))
async def test_get_parse_float(float_parser, mock_httpx_client):
    """Ensure parse_float is used when None"""
    _, _, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b'{"currency": 42.0}')
    inner(happy_result)

    sf_type = _create_sf_type()
    sf_type._parse_float = float_parser
    result = await sf_type.get(record_id='444')
    if float_parser is None:
        assert isinstance(result['currency'], float)
        assert result == {"currency": 42.0}
    elif float_parser is decimal.Decimal:
        assert isinstance(result['currency'], decimal.Decimal)
        assert result == {"currency": decimal.Decimal("42.0")}


@pytest.fixture
def fake_file(tmp_path):
    fl = tmp_path / "hello.txt"
    fl.write_text("hello")
    return str(tmp_path / "hello.txt")


@pytest.mark.asyncio
async def test_upload_base64(fake_file, mock_httpx_client):
    """
    Upload file as base64
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)
    sf_type = _create_sf_type()
    result = await sf_type.upload_base64(fake_file)
    assert result == happy_result
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == sf_type.base_url


@pytest.mark.asyncio
async def test_update_base64(fake_file, mock_httpx_client):
    """
    Update base64 file
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"{}")
    inner(happy_result)
    sf_type = _create_sf_type()
    result = await sf_type.update_base64("a1", fake_file)
    assert result == 200
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "PATCH"
    assert call[1][1] == f"{sf_type.base_url}a1"


@pytest.mark.asyncio
async def test_get_base64(mock_httpx_client):
    """
    Get base64 file
    """
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=b"hello")
    inner(happy_result)
    sf_type = _create_sf_type()
    result = await sf_type.get_base64("a1")
    assert result == b"hello"
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{sf_type.base_url}a1/Body"


# # # # # # # # # # # # # # # # # # # # # #
#
# AsyncSalesforce Tests
#
# # # # # # # # # # # # # # # # # # # # # #


def test_client_custom_version():
    """
    Check custom version appears in URL
    """
    expected_version = "4.2"
    client = AsyncSalesforce(version=expected_version)
    assert client.base_url.split("/")[-2] == "v%s" % expected_version


@pytest.mark.asyncio
async def test_async_retry_expired_session_deco(
    mock_httpx_client, sf_client,
):
    """Test that when SalesforceExpiredSession is thrown, it retries"""
    _, mock_client, _ = mock_httpx_client
    body1 = {"auth": "failed"}
    body2 = {"records": [{"ID": "1"}], "done": True, "totalSize": 1}
    responses = [
        httpx.Response(401, request=mock_client.request, content=json.dumps(body1)),
        httpx.Response(200, content=json.dumps(body2)),
    ]
    mock_client.request.side_effect = mock.AsyncMock(side_effect=responses)
    expected = {
        "totalSize": 1,
        "records": [OrderedDict([("ID", "1")])],
        "done": True,
    }

    # This should eagerly pull all results from all pages
    result = await sf_client.query_all("SELECT ID FROM Account")
    assert result == expected
    assert len(mock_client.method_calls) == 2
    # Check that login_refresh was called once
    assert sf_client.login_refresh.call_count == 1


@pytest.mark.asyncio
async def test_async_retry_expired_session_deco_sf_type(
    mock_httpx_client, sf_client,
):
    """Test that when SalesforceExpiredSession is thrown, AsyncSFType retries"""
    _, mock_client, _ = mock_httpx_client
    body1 = {"auth": "failed"}
    body2 = {"records": [{"ID": "1"}], "done": True, "totalSize": 1}
    responses = [
        httpx.Response(401, request=mock_client.request, content=json.dumps(body1)),
        httpx.Response(200, content=json.dumps(body2)),
    ]
    mock_client.request.side_effect = mock.AsyncMock(side_effect=responses)
    expected = {
        "totalSize": 1,
        "records": [OrderedDict([("ID", "1")])],
        "done": True,
    }
    sf_type = _create_sf_type()
    sf_type.salesforce = sf_client
    headers = None

    result = await sf_type.get(record_id="444", headers=headers)
    assert result == expected

    assert len(mock_client.method_calls) == 2
    # Check that login_refresh was called once
    assert sf_client.login_refresh.call_count == 1

    call1, call2 = mock_client.method_calls
    assert call1[1][0] == "GET"
    assert call2[1][0] == "GET"
    assert call1[1][1] == f"{CASE_URL}/444"
    assert call2[1][1] ==  f"{CASE_URL}/444"



# pylint: disable=protected-access
def test_proxies_inherited_by_default(constants):
    """
    Check session gets passed to AsyncSFType and proxies are inherited
    """
    client = AsyncSalesforce(
        session_id=constants["SESSION_ID"], proxies=constants["PROXIES"]
    )
    assert client._proxies == client.Contact._proxies == constants["PROXIES"]


@pytest.mark.asyncio
async def test_api_usage_simple(mock_httpx_client, sf_client):
    """
    Test simple api usage parsing
    """
    _, _, inner = mock_httpx_client
    happy_result = httpx.Response(
        200,
        content='{"example": 1}',
        headers={"Sforce-Limit-Info": "api-usage=18/5000"},
    )
    inner(happy_result)
    await sf_client.query("q")
    assert sf_client.api_usage == {"api-usage": Usage(18, 5000)}


@pytest.mark.asyncio
async def test_api_usage_per_app(mock_httpx_client, sf_client):
    """
    Test per-app api usage parsing
    """
    _, _, inner = mock_httpx_client
    pau = "api-usage=25/5000; per-app-api-usage=17/250(appName=sample-app)"
    happy_result = httpx.Response(
        200, content='{"example": 1}', headers={"Sforce-Limit-Info": pau}
    )
    inner(happy_result)
    await sf_client.query("q")
    expected = {
        "api-usage": Usage(25, 5000),
        "per-app-api-usage": PerAppUsage(17, 250, "sample-app"),
    }
    assert sf_client.api_usage == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "include_deleted,expected_url",
    ((True, "https://localhost/queryAll/"), (False, "https://localhost/query/"),),
)
async def test_query(
    include_deleted, expected_url, mock_httpx_client, sf_client,
):
    """Test querying generates the expected request"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content="{}")
    inner(happy_result)
    await sf_client.query("SELECT ID FROM Account", include_deleted=include_deleted)
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == expected_url
    assert call[2]["headers"] == {}
    assert call[2]["params"] == {"q": "SELECT ID FROM Account"}



@pytest.mark.asyncio
async def test_search(
    mock_httpx_client, sf_client,
):
    """Test querying generates the expected request"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content="{}")
    inner(happy_result)
    await sf_client.search("FIND {Joe Smith}")
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == "https://localhost/search/"
    assert call[2]["headers"] == {}
    assert call[2]["params"] == {"q": "FIND {Joe Smith}"}
    # Try the same with `quick_search`
    await sf_client.quick_search("Joe Smith")
    assert len(mock_client.method_calls) == 2
    call = mock_client.method_calls[-1]
    assert call[1][0] == "GET"
    assert call[1][1] == "https://localhost/search/"
    assert call[2]["headers"] == {}
    assert call[2]["params"] == {"q": "FIND {Joe Smith}"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "include_deleted,expected_url",
    (
        (True, "https://localhost/queryAll/next-records-id"),
        (False, "https://localhost/query/next-records-id"),
    ),
)
async def test_query_more_id_not_url(
    include_deleted, expected_url, mock_httpx_client, sf_client,
):
    """Test querying generates the expected request"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content="{}")
    inner(happy_result)
    await sf_client.query_more(
        "next-records-id", include_deleted=include_deleted, identifier_is_url=False
    )
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == expected_url
    assert call[2]["headers"] == {}


# pylint: disable=redefined-outer-name
@pytest.mark.asyncio
async def test_query_all_iter(
    mock_httpx_client, sf_client,
):
    """Test that we query and fetch additional result sets lazily."""
    _, mock_client, _ = mock_httpx_client
    body1 = {
        "records": [{"ID": "1"}],
        "done": False,
        "nextRecordsUrl": "https://example.com/query/next-records-id",
        "totalSize": 2,
    }
    body2 = {"records": [{"ID": "2"}], "done": True, "totalSize": 2}
    responses = [
        httpx.Response(200, content=json.dumps(body1)),
        httpx.Response(200, content=json.dumps(body2)),
    ]
    mock_client.request.side_effect = mock.AsyncMock(side_effect=responses)
    expected = [OrderedDict([("ID", "1")]), OrderedDict([("ID", "2")])]

    # This should return an Async Generator: collect responses and compare
    result = sf_client.query_all_iter("SELECT ID FROM Account")
    collection = []
    async for item in result:
        collection.append(item)

    assert collection == expected
    assert len(mock_client.method_calls) == 2


@pytest.mark.asyncio
async def test_is_sandbox(
    mock_httpx_client, sf_client,
):
    """Test that client can parse sandbox results."""
    _, mock_client, inner = mock_httpx_client
    body1 = {
        "records": [{"IsSandbox": True}],
        "done": True,
        "totalSize": 1,
    }
    happy_result = httpx.Response(200, content=json.dumps(body1))
    inner(happy_result)

    result = await sf_client.is_sandbox()
    assert result is True
    assert len(mock_client.method_calls) == 1


@pytest.mark.asyncio
async def test_describe(
    mock_httpx_client, sf_client,
):
    """Test describe call."""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content="[{}]")
    inner(happy_result)

    result = await sf_client.describe()
    assert result
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == f"{sf_client.base_url}sobjects"
    assert call[2]["headers"] == {}


@pytest.mark.asyncio
async def test_query_all(
    mock_httpx_client, sf_client,
):
    """Test that we query and fetch additional result sets automatically."""
    _, mock_client, _ = mock_httpx_client
    body1 = {
        "records": [{"ID": "1"}],
        "done": False,
        "nextRecordsUrl": "https://example.com/query/next-records-id",
        "totalSize": 2,
    }
    body2 = {"records": [{"ID": "2"}], "done": True, "totalSize": 2}
    responses = [
        httpx.Response(200, content=json.dumps(body1)),
        httpx.Response(200, content=json.dumps(body2)),
    ]
    mock_client.request.side_effect = mock.AsyncMock(side_effect=responses)
    expected = {
        "totalSize": 2,
        "records": [OrderedDict([("ID", "1")]), OrderedDict([("ID", "2")])],
        "done": True,
    }

    # This should eagerly pull all results from all pages
    result = await sf_client.query_all("SELECT ID FROM Account")
    assert result == expected
    assert len(mock_client.method_calls) == 2


@pytest.mark.asyncio
async def test_api_limits(
    constants, mock_httpx_client, sf_client,
):
    """Test method for getting Salesforce organization limits"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(
        200, content=json.dumps(constants["ORGANIZATION_LIMITS_RESPONSE"])
    )
    inner(happy_result)
    result = await sf_client.limits()
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "GET"
    assert call[1][1] == "https://localhost/limits/"
    assert result == constants["ORGANIZATION_LIMITS_RESPONSE"]


@pytest.mark.asyncio
async def test_md_deploy_success(
    mock_httpx_client, sf_client,
):
    """Test method for metadata deployment"""
    mock_response = (
        '<?xml version="1.0" '
        'encoding="UTF-8"?><soapenv:Envelope '
        'xmlns:soapenv="http://schemas.xmlsoap.org/soap'
        '/envelope/" '
        'xmlns="http://soap.sforce.com/2006/04/metadata'
        '"><soapenv:Body><deployResponse><result><done'
        ">false</done><id>0Af3B00001CMyfASAT</id><state"
        ">Queued</state></result></deployResponse></soapenv"
        ":Body></soapenv:Envelope>"
    )

    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=mock_response)
    inner(happy_result)
    async with aiofiles.tempfile.NamedTemporaryFile("wb+") as fl:
        await fl.write(b"Line1\n Line2")
        await fl.seek(0)
        result = await sf_client.deploy(fl.name, sandbox=False)
    assert result.get("asyncId") == "0Af3B00001CMyfASAT"
    assert result.get("state") == "Queued"

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == f"{sf_client.metadata_url}deployRequest"


@pytest.mark.asyncio
async def test_md_deploy_failed_status_code(
    mock_httpx_client, sf_client,
):
    """Test method for metadata deployment on Failure"""
    _, _, inner = mock_httpx_client
    bad_result = httpx.Response(
        2599,
        request=httpx.Request("POST", f"{sf_client.metadata_url}deployRequest"),
        content=b"Unrecognized Error",
    )
    inner(bad_result)
    async with aiofiles.tempfile.NamedTemporaryFile("wb+") as fl:
        await fl.write(b"Line1\n Line2")
        await fl.seek(0)
        with pytest.raises(SalesforceGeneralError):
            await sf_client.deploy(fl.name, sandbox=False)


DEPLOY_PENDING = (
    '<?xml version="1.0" '
    'encoding="UTF-8"?><soapenv:Envelope '
    'xmlns:soapenv="http://schemas.xmlsoap.org/soap'
    '/envelope/" '
    'xmlns="http://soap.sforce.com/2006/04/metadata'
    '"><soapenv:Body><checkDeployStatusResponse><result'
    "><checkOnly>true</checkOnly><createdBy"
    ">0053D0000052Xaq</createdBy><createdByName>User "
    "User</createdByName><createdDate>2020-10-28T15:38:34"
    ".000Z</createdDate><details><runTestResult"
    "><numFailures>0</numFailures><numTestsRun>0"
    "</numTestsRun><totalTime>0.0</totalTime"
    "></runTestResult></details><done>false</done><id"
    ">0Af3D00001NViC1SAL</id><ignoreWarnings>false"
    "</ignoreWarnings><lastModifiedDate>2020-10-28T15:38"
    ":34.000Z</lastModifiedDate><numberComponentErrors>0"
    "</numberComponentErrors><numberComponentsDeployed>0"
    "</numberComponentsDeployed><numberComponentsTotal>0"
    "</numberComponentsTotal><numberTestErrors>0"
    "</numberTestErrors><numberTestsCompleted>0"
    "</numberTestsCompleted><numberTestsTotal>0"
    "</numberTestsTotal><rollbackOnError>true"
    "</rollbackOnError><runTestsEnabled>false"
    "</runTestsEnabled><status>Pending</status><success"
    ">false</success></result></checkDeployStatusResponse"
    "></soapenv:Body></soapenv:Envelope>"
)

DEPLOY_SUCCESS = (
    '<?xml version="1.0" '
    'encoding="UTF-8"?><soapenv:Envelope '
    'xmlns:soapenv="http://schemas.xmlsoap.org/soap'
    '/envelope/" '
    'xmlns="http://soap.sforce.com/2006/04/metadata'
    '"><soapenv:Body><checkDeployStatusResponse><result'
    "><checkOnly>false</checkOnly><completedDate>2020-10"
    "-28T13:33:29.000Z</completedDate><createdBy"
    ">0053D0000052Xaq</createdBy><createdByName>User "
    "User</createdByName><createdDate>2020-10-28T13:33:25"
    ".000Z</createdDate><details><componentSuccesses"
    "><changed>true</changed><componentType>ApexSettings"
    "</componentType><created>false</created><createdDate"
    ">2020-10-28T13:33:29.000Z</createdDate><deleted"
    ">false</deleted><fileName>shape/settings/Apex"
    ".settings</fileName><fullName>Apex</fullName"
    "><success>true</success></componentSuccesses"
    "><componentSuccesses><changed>true</changed"
    "><componentType>ChatterSettings</componentType"
    "><created>false</created><createdDate>2020-10-28T13"
    ":33:29.000Z</createdDate><deleted>false</deleted"
    "><fileName>shape/settings/Chatter.settings</fileName"
    "><fullName>Chatter</fullName><success>true</success"
    "></componentSuccesses><componentSuccesses><changed"
    ">true</changed><componentType></componentType"
    "><created>false</created><createdDate>2020-10-28T13"
    ":33:29.000Z</createdDate><deleted>false</deleted"
    "><fileName>shape/package.xml</fileName><fullName"
    ">package.xml</fullName><success>true</success"
    "></componentSuccesses><componentSuccesses><changed"
    ">true</changed><componentType>LightningExperienceSettings"
    "</componentType><created>false</created><createdDate>"
    "2020-10-28T13:33:29.000Z</createdDate><deleted>false"
    "</deleted><fileName>shape/settings/LightningExperience."
    "settings</fileName><fullName>LightningExperience</fullName>"
    "<success>true</success></componentSuccesses><component"
    "Successes><changed>true</changed><componentType>LanguageSettings"
    "</componentType><created>false</created><createdDate>"
    "2020-10-28T13:33:29.000Z</createdDate><deleted>false</deleted>"
    "<fileName>shape/settings/Language.settings</fileName>"
    "<fullName>Language</fullName><success>true</success>"
    "</componentSuccesses><runTestResult><numFailures>0</numFailures>"
    "<numTestsRun>0</numTestsRun><totalTime>0.0</totalTime>"
    "</runTestResult></details><done>true</done><id>0Af3D00001NVCnwSAH"
    "</id><ignoreWarnings>false</ignoreWarnings><lastModifiedDate>"
    "2020-10-28T13:33:29.000Z</lastModifiedDate>"
    "<numberComponentErrors>0</numberComponentErrors>"
    "<numberComponentsDeployed>4</numberComponentsDeployed>"
    "<numberComponentsTotal>4</numberComponentsTotal>"
    "<numberTestErrors>0</numberTestErrors><numberTestsCompleted>"
    "0</numberTestsCompleted><numberTestsTotal>0</numberTestsTotal>"
    "<rollbackOnError>true</rollbackOnError><runTestsEnabled>false"
    "</runTestsEnabled><startDate>2020-10-28T13:33:26.000Z</startDate>"
    "<status>Succeeded</status><success>true</success></result>"
    "</checkDeployStatusResponse></soapenv:Body></soapenv:Envelope>"
)
DEPLOY_PAYLOAD_ERROR = (
    '<?xml version="1.0" '
    'encoding="UTF-8"?><soapenv:Envelope '
    'xmlns:soapenv="http://schemas.xmlsoap.org/soap'
    '/envelope/" '
    'xmlns="http://soap.sforce.com/2006/04/metadata'
    '"><soapenv:Body><checkDeployStatusResponse><result'
    "><checkOnly>true</checkOnly><completedDate>2020-10"
    "-28T13:37:48.000Z</completedDate><createdBy"
    ">0053D0000052Xaq</createdBy><createdByName>User "
    "User</createdByName><createdDate>2020-10-28T13:37:46"
    ".000Z</createdDate><details><componentFailures"
    "><changed>false</changed><componentType"
    "></componentType><created>false</created"
    "><createdDate>2020-10-28T13:37:47.000Z</createdDate"
    "><deleted>false</deleted><fileName>package.xml"
    "</fileName><fullName>package.xml</fullName><problem"
    ">No package.xml "
    "found</problem><problemType>Error</problemType"
    "><success>false</success></componentFailures"
    "><runTestResult><numFailures>0</numFailures"
    "><numTestsRun>0</numTestsRun><totalTime>0.0"
    "</totalTime></runTestResult></details><done>true"
    "</done><id>0Af3D00001NVD0TSAX</id><ignoreWarnings"
    ">false</ignoreWarnings><lastModifiedDate>2020-10"
    "-28T13:37:48.000Z</lastModifiedDate"
    "><numberComponentErrors>0</numberComponentErrors"
    "><numberComponentsDeployed>0</numberComponentsDeployed><numberComponentsTotal>0</numberComponentsTotal><numberTestErrors>0</numberTestErrors><numberTestsCompleted>0</numberTestsCompleted><numberTestsTotal>0</numberTestsTotal><rollbackOnError>true</rollbackOnError><runTestsEnabled>false</runTestsEnabled><startDate>2020-10-28T13:37:47.000Z</startDate><status>Failed</status><success>false</success></result></checkDeployStatusResponse></soapenv:Body></soapenv:Envelope>"
)

DEPLOY_IN_PROGRESS = (
    '<?xml version="1.0" '
    'encoding="UTF-8"?><soapenv:Envelope '
    'xmlns:soapenv="http://schemas.xmlsoap.org/soap'
    '/envelope/" '
    'xmlns="http://soap.sforce.com/2006/04/metadata'
    '"><soapenv:Body><checkDeployStatusResponse><result'
    "><checkOnly>false</checkOnly><createdBy"
    ">0053D0000052Xaq</createdBy><createdByName>User "
    "User</createdByName><createdDate>2020-10-28T17:24:30"
    ".000Z</createdDate><details><runTestResult"
    "><numFailures>0</numFailures><numTestsRun>0"
    "</numTestsRun><totalTime>0.0</totalTime"
    "></runTestResult></details><done>false</done><id"
    ">0Af3D00001NW8mnSAD</id><ignoreWarnings>false"
    "</ignoreWarnings><lastModifiedDate>2020-10-28T17:37"
    ":08.000Z</lastModifiedDate><numberComponentErrors>0"
    "</numberComponentErrors><numberComponentsDeployed>2"
    "</numberComponentsDeployed><numberComponentsTotal>3"
    "</numberComponentsTotal><numberTestErrors>0"
    "</numberTestErrors><numberTestsCompleted>0"
    "</numberTestsCompleted><numberTestsTotal>0"
    "</numberTestsTotal><rollbackOnError>true"
    "</rollbackOnError><runTestsEnabled>false"
    "</runTestsEnabled><startDate>2020-10-28T17:24:30"
    ".000Z</startDate><status>InProgress</status><success"
    ">false</success></result></checkDeployStatusResponse"
    "></soapenv:Body></soapenv:Envelope>"
)


@pytest.mark.asyncio
async def test_check_status_pending(
    mock_httpx_client, sf_client,
):
    """Test method for metadata deployment"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=DEPLOY_PENDING)
    inner(happy_result)

    result = await sf_client.checkDeployStatus("abdcefg", sandbox=False)
    assert result.get("state") == "Pending"
    assert result.get("state_detail") is None
    assert result.get("deployment_detail") == {
        "total_count": "0",
        "failed_count": "0",
        "deployed_count": "0",
        "errors": [],
    }
    assert result.get("unit_test_detail") == {
        "total_count": "0",
        "failed_count": "0",
        "completed_count": "0",
        "errors": [],
    }

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == f"{sf_client.metadata_url}deployRequest/abdcefg"


@pytest.mark.asyncio
async def test_check_status_success(
    mock_httpx_client, sf_client,
):
    """Test method for metadata deployment"""

    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=DEPLOY_SUCCESS)
    inner(happy_result)

    result = await sf_client.checkDeployStatus("abdcefg", sandbox=False)
    assert result.get("state") == "Succeeded"
    assert result.get("state_detail") is None
    assert result.get("deployment_detail") == {
        "total_count": "4",
        "failed_count": "0",
        "deployed_count": "4",
        "errors": [],
    }
    assert result.get("unit_test_detail") == {
        "total_count": "0",
        "failed_count": "0",
        "completed_count": "0",
        "errors": [],
    }

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == f"{sf_client.metadata_url}deployRequest/abdcefg"


@pytest.mark.asyncio
async def test_check_status_payload_error(
    mock_httpx_client, sf_client,
):
    """Test method for metadata deployment"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=DEPLOY_PAYLOAD_ERROR)
    inner(happy_result)

    result = await sf_client.checkDeployStatus("abdcefg", sandbox=False)
    assert result.get("state") == "Failed"
    assert result.get("state_detail") is None
    assert result.get("deployment_detail") == {
        "total_count": "0",
        "failed_count": "0",
        "deployed_count": "0",
        "errors": [
            {
                "type": None,
                "file": "package.xml",
                "status": "Error",
                "message": "No package.xml found",
            }
        ],
    }
    assert result.get("unit_test_detail") == {
        "total_count": "0",
        "failed_count": "0",
        "completed_count": "0",
        "errors": [],
    }
    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == f"{sf_client.metadata_url}deployRequest/abdcefg"


@pytest.mark.asyncio
async def test_check_status_in_progress(
    mock_httpx_client, sf_client,
):
    """Test method for metadata deployment"""
    _, mock_client, inner = mock_httpx_client
    happy_result = httpx.Response(200, content=DEPLOY_IN_PROGRESS)
    inner(happy_result)

    result = await sf_client.checkDeployStatus("abdcefg", sandbox=False)
    assert result.get("state") == "InProgress"
    assert result.get("state_detail") is None
    assert result.get("deployment_detail") == {
        "total_count": "3",
        "failed_count": "0",
        "deployed_count": "2",
        "errors": [],
    }
    assert result.get("unit_test_detail") == {
        "total_count": "0",
        "failed_count": "0",
        "completed_count": "0",
        "errors": [],
    }

    assert len(mock_client.method_calls) == 1
    call = mock_client.method_calls[0]
    assert call[1][0] == "POST"
    assert call[1][1] == f"{sf_client.metadata_url}deployRequest/abdcefg"

@pytest.mark.asyncio
async def test_restful(
    mock_httpx_client, sf_client,
):
    """Test that client can parse sandbox results."""
    _, mock_client, inner = mock_httpx_client
    body1 = {
        "records": [{"IsSandbox": True}],
        "done": True,
        "totalSize": 1,
    }
    happy_result = httpx.Response(200, content=json.dumps(body1))
    inner(happy_result)

    result = await sf_client.restful("/sobjects/User/ABC123/password", params={"hey": "now"})
    assert result == body1
    assert len(mock_client.method_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ("application/json", ""))
async def test_oauth2_with_or_without_json_result(
    content_type, mock_httpx_client, sf_client,
):
    """Test that client can parse sandbox results."""
    _, mock_client, inner = mock_httpx_client
    body1 = {
        "records": [{"IsSandbox": True}],
        "done": True,
        "totalSize": 1,
    }
    happy_result = httpx.Response(
        200, headers={"Content-Type": content_type}, content=json.dumps(body1)
    )
    inner(happy_result)

    result = await sf_client.oauth2("/services/oauth2/token", params={"hey": "now"})
    if not content_type:
        assert result is None
    else:
        assert result == body1
    assert len(mock_client.method_calls) == 1


# # Parsing Results Tests # #


@pytest.mark.asyncio
@pytest.mark.parametrize("float_parser", (None, decimal.Decimal))
@pytest.mark.parametrize("object_pairs_hook", (None, OrderedDict))
async def test_json_parsing_stratgies(
    float_parser, object_pairs_hook, mock_httpx_client, sf_client,
):
    """Test parsing float strategies"""
    _, _, inner = mock_httpx_client
    sf_client._parse_float = float_parser
    sf_client._object_pairs_hook = object_pairs_hook
    happy_result = httpx.Response(200, content=b'{"currency": 1.0}')
    inner(happy_result)
    result = await sf_client.query("SELECT ID FROM Account")
    if object_pairs_hook is None:
        assert isinstance(result, dict)
    else:
        assert isinstance(result, object_pairs_hook)

    if float_parser is None:
        assert isinstance(result['currency'], float)
        assert result == {"currency": 1.0}
    elif float_parser is decimal.Decimal:
        assert isinstance(result['currency'], decimal.Decimal)
        assert result == {"currency": decimal.Decimal("1.0")}
