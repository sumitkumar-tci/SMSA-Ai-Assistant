from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
import xmltodict
from pydantic import BaseModel

from ..models.tracking import TrackingCheckpoint, TrackingResult, TrackingStatus
from ..config.settings import settings
from ..logging_config import logger


class SMSAAIAssistantSMSATrackingClientConfig(BaseModel):
    username: str
    password: str
    base_url: str


class SMSAAIAssistantSMSATrackingClient:
    """
    Async client for SMSA Tracking SOAP API using the credentials and payload
    structure provided in the project reference.
    """

    def __init__(self, config: Optional[SMSAAIAssistantSMSATrackingClientConfig] = None) -> None:
        if config is None:
            config = SMSAAIAssistantSMSATrackingClientConfig(
                username=settings.smsa_tracking_username,
                password=settings.smsa_tracking_password,
                base_url=settings.smsa_tracking_base_url,
            )
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(connect=5, total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _post_soap(
        self, action: str, envelope: str
    ) -> str:
        session = await self._get_session()
        headers = {
            "Content-Type": "text/xml",
            "SOAPAction": action,
        }
        async with session.post(
            self._config.base_url,
            data=envelope.encode("utf-8"),
            headers=headers,
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"SMSA tracking API error {resp.status}: {text[:200]}"
                )
        return text

    def _normalize_status_text(self, status_code: str, event_desc: str) -> str:
        """
        Convert SMSA status codes to a user-friendly status string for display.
        """
        friendly_map = {
            # Delivery statuses
            "DLV": "Delivered",
            "DEL": "Delivered",
            "DELIVERED": "Delivered",
            # Return statuses
            "RTS": "Returned to Shipper",
            "RTN": "Returned",
            "RETURNED": "Returned",
            # In transit statuses
            "PU": "Picked Up",
            "PICKUP": "Picked Up",
            "AF": "Arrived at Facility",
            "ARRIVED": "Arrived at Facility",
            "HIP": "At Sorting Hub",
            "HOP": "Departed Hub",
            "INT": "In Transit",
            "TRANSIT": "In Transit",
            # Delivery attempt / special process
            "OFD": "Out for Delivery",
            "OUT FOR DELIVERY": "Out for Delivery",
            "DEX14": "Return in Progress",
            "DEX29": "Rerouted",
            # Collection
            "RTI": "Ready for Collection",
            "RTOPS": "Collected from Retail",
            # Notification
            "SMS": "SMS Notification Sent",
            # Other
            "HOLD": "On Hold",
            "CAN": "Cancelled",
            "CANCELLED": "Cancelled",
        }
        code = (status_code or "").upper()
        if code in friendly_map:
            return friendly_map[code]
        if event_desc and event_desc != "Unknown":
            return event_desc
        return code or "UNKNOWN"

    def _map_status_to_enum(self, status_code: str) -> TrackingStatus:
        """
        Map SMSA status code into our limited TrackingStatus enum.
        """
        code = (status_code or "").upper()
        if code in {"DLV", "DEL", "DELIVERED"}:
            return "DELIVERED"
        if code in {"OFD", "OUT FOR DELIVERY"}:
            return "OUT_FOR_DELIVERY"
        if code in {"PU", "PICKUP", "AF", "ARRIVED", "HIP", "HOP", "INT", "TRANSIT"}:
            return "IN_TRANSIT"
        if code in {"RTS", "RTN", "RETURNED", "DEX14", "DEX29", "HOLD", "CAN", "CANCELLED"}:
            return "EXCEPTION"
        return "UNKNOWN"

    def _parse_tracking_details(self, xml_text: str, awb: str) -> Dict[str, Any]:
        """
        Parse SMSA SOAP XML according to the real TrackRslt structure:

        Envelope -> Body -> getSMSATrackingDetailsResponse ->
        getSMSATrackingDetailsResult -> TrackRslt[*]
        """
        try:
            parsed = xmltodict.parse(xml_text)
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "error": f"Failed to parse SMSA tracking XML: {exc}",
                "awb": awb,
            }

        envelope = parsed.get("s:Envelope") or parsed.get("soap:Envelope")
        if not isinstance(envelope, dict):
            return {"error": "No SOAP envelope found", "awb": awb}

        body = envelope.get("s:Body") or envelope.get("soap:Body")
        if not isinstance(body, dict):
            return {"error": "No SOAP body found", "awb": awb}

        # SOAP Fault handling
        fault = body.get("s:Fault") or body.get("soap:Fault")
        if isinstance(fault, dict):
            fault_msg = (
                fault.get("faultstring")
                or fault.get("faultString")
                or "Unknown SOAP fault"
            )
            return {
                "error": f"SMSA SOAP fault: {fault_msg}",
                "awb": awb,
            }

        tracking_response = body.get("getSMSATrackingDetailsResponse")
        if not isinstance(tracking_response, dict):
            return {"error": "No tracking response found", "awb": awb}

        result = tracking_response.get("getSMSATrackingDetailsResult")
        if not isinstance(result, dict):
            return {"error": "No tracking result found", "awb": awb}

        track_results = result.get("TrackRslt")
        if not track_results:
            return {
                "error": "No tracking events found for this AWB",
                "awb": awb,
            }

        # Ensure list
        if not isinstance(track_results, list):
            track_results = [track_results]

        latest_event = track_results[0]
        if not isinstance(latest_event, dict):
            return {
                "error": "Invalid tracking event structure",
                "awb": awb,
            }

        event_desc = latest_event.get("EventDesc", "Unknown")
        office = latest_event.get("Office", "N/A")
        event_time = latest_event.get("EventTime", "")
        status_code = latest_event.get("StatusCode", "UNKNOWN")
        country_code = latest_event.get("CountryCode", "")

        # Parse timestamp
        date_str = ""
        time_str = ""
        if event_time:
            try:
                dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                date_str = event_time

        status_text = self._normalize_status_text(status_code, event_desc)

        history: List[Dict[str, Any]] = []
        for ev in track_results:
            if not isinstance(ev, dict):
                continue
            ev_time = ev.get("EventTime", "")
            ev_date_str = ""
            ev_time_only = ""
            if ev_time:
                try:
                    dt_ev = datetime.fromisoformat(ev_time.replace("Z", "+00:00"))
                    ev_date_str = dt_ev.strftime("%Y-%m-%d")
                    ev_time_only = dt_ev.strftime("%H:%M:%S")
                except Exception:
                    ev_date_str = ev_time

            history.append(
                {
                    "description": ev.get("EventDesc", "Unknown"),
                    "location": ev.get("Office", "N/A"),
                    "status_code": ev.get("StatusCode", ""),
                    "date": ev_date_str,
                    "time": ev_time_only,
                    "country": ev.get("CountryCode", ""),
                    "timestamp": ev.get("EventTime", ""),
                }
            )

        return {
            "awb": awb,
            "status": status_text,
            "status_code": status_code,
            "location": office or "N/A",
            "country": country_code or "",
            "description": event_desc,
            "date": date_str,
            "time": time_str,
            "timestamp": event_time,
            "history": history,
        }

    async def track_single(self, awb: str, lang: str = "en") -> TrackingResult:
        """
        Call the real SMSA single tracking SOAP API for one AWB and map the
        response to TrackingResult.
        """
        envelope = f"""
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/">
  <soapenv:Header/>
  <soapenv:Body>
    <tem:getSMSATrackingDetails>
      <tem:lang>{lang}</tem:lang>
      <tem:awb>{awb}</tem:awb>
      <tem:username>{self._config.username}</tem:username>
      <tem:password>{self._config.password}</tem:password>
    </tem:getSMSATrackingDetails>
  </soapenv:Body>
</soapenv:Envelope>
""".strip()

        try:
            xml_text = await self._post_soap(
                "http://tempuri.org/iTrack/getSMSATrackingDetails", envelope
            )
        except Exception as exc:
            # Bubble up as a structured error in the result
            return TrackingResult(
                awb=awb,
                status="EXCEPTION",
                checkpoints=[],
                error_code="API_ERROR",
                error_message=str(exc),
                raw_response=None,
            )

        details = self._parse_tracking_details(xml_text, awb)
        if "error" in details:
            return TrackingResult(
                awb=details.get("awb") or awb,
                status="EXCEPTION",
                checkpoints=[],
                error_code="PARSE_ERROR",
                error_message=str(details.get("error")),
                raw_response=details,  # type: ignore[arg-type]
            )

        status_text = details.get("status") or "UNKNOWN"
        location_text = details.get("location") or "N/A"
        status_code = details.get("status_code") or ""
        status_enum = self._map_status_to_enum(status_code)

        # Build checkpoints from history
        checkpoints: List[TrackingCheckpoint] = []
        history = details.get("history") or []
        if isinstance(history, list) and history:
            for ev in history:
                if not isinstance(ev, dict):
                    continue
                ts_str = ev.get("timestamp") or ""
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    ts = datetime.now(timezone.utc)
                checkpoints.append(
                    TrackingCheckpoint(
                        timestamp=ts,
                        location=ev.get("location") or "Unknown location",
                        description=ev.get("description") or "Status update",
                        statusCode=ev.get("status_code"),
                    )
                )
        else:
            checkpoints.append(
                TrackingCheckpoint(
                    timestamp=datetime.now(timezone.utc),
                    location=location_text,
                    description=status_text,
                    statusCode=details.get("status_code"),
                )
            )

        return TrackingResult(
            awb=details.get("awb") or awb,
            status=status_enum,
            currentLocation=location_text,  # type: ignore[arg-type]
            checkpoints=checkpoints,
            rawResponse=details,  # type: ignore[arg-type]
        )

    async def track_bulk(
        self, awbs: List[str], lang: str = "en"
    ) -> List[TrackingResult]:
        """
        Call the bulk tracking SOAP API. For simplicity and robustness, this
        implementation currently calls the single-tracking API per AWB
        concurrently, which is still efficient for a moderate number of AWBs.

        If needed, we can switch to the getBulkTracking SOAP action later.
        """
        tasks = [self.track_single(awb, lang=lang) for awb in awbs]
        return await asyncio.gather(*tasks)


class SMSAAIAssistantSMSARatesClient:
    """
    Async client for SMSA Rates Inquiry REST API.

    Endpoint: POST https://mobileapi.smsaexpress.com/SmsaMobileWebServiceRestApi/api/RateInquiry/inquiry
    Headers: Content-Type: application/json, Passkey: <from env SMSA_RATES_PASSKEY>
    """

    def __init__(self) -> None:
        from ..config.settings import get_settings
        from ..logging_config import logger

        settings = get_settings()
        self._base_url = settings.smsa_rates_base_url
        self._passkey = settings.smsa_rates_passkey
        
        # Log if passkey is missing
        if not self._passkey:
            logger.warning("rates_passkey_missing", message="SMSA Rates passkey is not configured in .env file")
        
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(connect=5, total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_rate(
        self,
        from_country: str,
        to_country: str,
        origin_city: str,
        destination_city: str,
        weight: str,
        pieces: str = "1",
        service_type: Optional[str] = None,
        language: str = "En",
    ) -> Dict[str, Any]:
        """
        Get shipping rates from SMSA Rates API.

        Args:
            from_country: Origin country code (e.g., "SA")
            to_country: Destination country code (e.g., "SA")
            origin_city: Origin city name (e.g., "Riyadh")
            destination_city: Destination city name (e.g., "Jeddah")
            weight: Weight as string (e.g., "1")
            pieces: Number of pieces as string (e.g., "1") - not used in API but kept for compatibility
            service_type: Optional service type - not used in actual API
            language: Language code "En" or "Ar" (default: "En")

        Returns:
            Dict with success, rates data, and error info if any.
        """
        from ..models.rates import RateInquiryRequest, RateInquiryResponse, RateResult

        session = await self._get_session()

        # Validate passkey
        if not self._passkey:
            from ..logging_config import logger
            logger.error("rates_passkey_missing", message="Cannot make API call without passkey")
            return RateResult(
                success=False,
                error_code="CONFIG_ERROR",
                error_message="Rates API passkey is not configured. Please check .env file.",
            ).model_dump(by_alias=True)

        # Build request payload - MUST match actual API format (lowercase field names)
        payload = {
            "fromCountry": from_country,
            "fromCity": origin_city,
            "toCountry": to_country,
            "toCity": destination_city,
            "documents": "documents",  # Required field
            "productcategory": "Parcel",  # Required field
            "weight": weight,  # Must be string
            "passkey": self._passkey,  # Passkey in body, not header
            "language": language,  # "En" or "Ar"
        }

        headers = {
            "Content-Type": "application/json",
        }

        try:
            from ..logging_config import logger
            # Avoid logging sensitive secrets like the raw passkey
            safe_payload = {**payload, "passkey": "***"}
            logger.info("rates_api_request", payload=safe_payload, url=self._base_url)
            
            async with session.post(
                self._base_url, json=payload, headers=headers
            ) as resp:
                response_text = await resp.text()
                logger.info("rates_api_response", status=resp.status, response_preview=response_text[:500])
                
                if resp.status != 200:
                    return RateResult(
                        success=False,
                        error_code="HTTP_ERROR",
                        error_message=f"SMSA rates API error {resp.status}: {response_text[:200]}",
                    ).model_dump(by_alias=True)

                # Parse JSON response
                try:
                    json_data = await resp.json()
                except Exception as json_error:
                    logger.error("rates_api_json_parse_error", error=str(json_error), response_text=response_text[:500])
                    return RateResult(
                        success=False,
                        error_code="JSON_PARSE_ERROR",
                        error_message=f"Invalid JSON response from API: {str(json_error)}",
                    ).model_dump(by_alias=True)

                logger.info("rates_api_json_data", json_data=json_data)

                # Parse response using Pydantic model
                # API returns: {"Success": bool, "Data": [...]}
                try:
                    api_response = RateInquiryResponse(**json_data)
                except Exception as pydantic_error:
                    logger.error(
                        "rates_api_pydantic_error",
                        error=str(pydantic_error),
                        json_data=json_data,
                    )
                    return RateResult(
                        success=False,
                        error_code="MODEL_PARSE_ERROR",
                        error_message=f"Failed to parse API response: {str(pydantic_error)}",
                    ).model_dump(by_alias=True)

                # Access fields directly - Pydantic models use the field name as attribute
                # API returns: {"Success": bool, "Data": [...]}
                success = api_response.Success
                data_list = api_response.Data

                # Convert to agent-friendly format
                rates = []
                for rate_option in data_list:
                    rates.append(
                        {
                            "product": rate_option.Product,
                            "productCode": rate_option.ProductCode,
                            "amount": rate_option.Amount,
                            "vatAmount": rate_option.VatAmount,
                            "totalAmount": rate_option.TotalAmount,
                            "vatPercentage": rate_option.VatPercentage,
                            "currency": rate_option.Currency,
                        }
                    )

                logger.info("rates_api_success", rates_count=len(rates), success=success)
                return RateResult(
                    success=success,
                    rates=rates,
                ).model_dump(by_alias=True)

        except aiohttp.ClientError as e:
            from ..logging_config import logger
            logger.error("rates_api_network_error", error=str(e), url=self._base_url)
            return RateResult(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=f"Failed to connect to SMSA rates API: {e}",
            ).model_dump(by_alias=True)
        except Exception as e:
            from ..logging_config import logger
            import traceback
            logger.error(
                "rates_api_parse_error",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return RateResult(
                success=False,
                error_code="PARSE_ERROR",
                error_message=f"Failed to parse SMSA rates response: {str(e)}",
            ).model_dump(by_alias=True)


class SMSAAIAssistantSMSARetailCentersClient:
    """
    Async client for SMSA Retail Centers / Service Centers API.

    Endpoint: https://mobileapi.smsaexpress.com/smsamobilepro/retailcenter.asmx
    SOAP service with 5 operations:
    1. ListOfCountries - Get all countries
    2. ListOfCities - Get cities by country code
    3. ListOfRetailCities - Get retail cities by country code
    4. ListOfCenters - Get centers by country and city (returns Lat-Long)
    5. ServiceCenterByCode - Get center by code
    """

    def __init__(self) -> None:
        self._base_url = settings.smsa_retail_base_url
        self._passkey = settings.smsa_retail_passkey
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(connect=5, total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _post_soap(
        self, action: str, envelope: str
    ) -> str:
        """Post SOAP envelope to the retail centers endpoint."""
        session = await self._get_session()
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": action,
            "Passkey": self._passkey,
        }
        async with session.post(
            self._base_url,
            data=envelope.encode("utf-8"),
            headers=headers,
        ) as resp:
            # Get response text first to see error details
            response_text = await resp.text()
            
            # If status is not OK, log the response for debugging
            if resp.status != 200:
                logger.error(
                    "soap_api_error",
                    status=resp.status,
                    action=action,
                    response_preview=response_text[:500],
                )
                # Try to parse SOAP fault if present
                try:
                    parsed = xmltodict.parse(response_text)
                    fault = parsed.get("soap:Envelope", {}).get("soap:Body", {}).get("soap:Fault", {})
                    if fault:
                        fault_string = fault.get("faultstring") or fault.get("soap:Fault", {}).get("faultstring", "")
                        error_msg = f"SOAP Fault: {fault_string}"
                        raise aiohttp.ClientResponseError(
                            request_info=resp.request_info,
                            history=resp.history,
                            status=resp.status,
                            message=error_msg,
                        )
                except Exception:
                    pass  # If parsing fails, use original error
            
            resp.raise_for_status()
            return response_text

    async def list_of_countries(self) -> Dict[str, Any]:
        """Get list of all countries."""
        soap_action = "https://mobileapi.smsaexpress.com/smsamobilepro/ListOfCountries"
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <ListOfCountries xmlns="https://mobileapi.smsaexpress.com/smsamobilepro/">
      <language>English</language>
      <passkey>{self._passkey}</passkey>
    </ListOfCountries>
  </soap:Body>
</soap:Envelope>"""
        try:
            xml_text = await self._post_soap(soap_action, envelope)
            parsed = xmltodict.parse(xml_text)
            body = parsed.get("soap:Envelope", {}).get("soap:Body", {})
            response = body.get("ListOfCountriesResponse", {}).get("ListOfCountriesResult", {})
            countries = []
            if isinstance(response, dict):
                country_list = response.get("countryRes", [])
                if not isinstance(country_list, list):
                    country_list = [country_list] if country_list else []
                
                for country_item in country_list:
                    if isinstance(country_item, dict):
                        countries.append({
                            "name": str(country_item.get("Country") or ""),
                            "code": str(country_item.get("Ccode") or ""),
                            "is_from": (country_item.get("IsFrom") or "False") == "True",
                        })
            return {"success": True, "countries": countries}
        except Exception as e:
            logger.error("list_of_countries_error", error=str(e), exc_info=True)
            return {"success": False, "error_message": str(e), "countries": []}

    async def list_of_cities(self, country: str = "SA") -> Dict[str, Any]:
        """Get list of cities by country code."""
        soap_action = "https://mobileapi.smsaexpress.com/smsamobilepro/ListOfCities"
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <ListOfCities xmlns="https://mobileapi.smsaexpress.com/smsamobilepro/">
      <country>{country}</country>
      <language>English</language>
      <passkey>{self._passkey}</passkey>
    </ListOfCities>
  </soap:Body>
</soap:Envelope>"""
        try:
            xml_text = await self._post_soap(soap_action, envelope)
            parsed = xmltodict.parse(xml_text)
            body = parsed.get("soap:Envelope", {}).get("soap:Body", {})
            response = body.get("ListOfCitiesResponse", {}).get("ListOfCitiesResult", {})
            cities = []
            if isinstance(response, dict):
                city_list = response.get("CitiesRes", [])
                if not isinstance(city_list, list):
                    city_list = [city_list] if city_list else []
                
                for city_item in city_list:
                    if isinstance(city_item, dict):
                        cities.append({
                            "name": str(city_item.get("City") or ""),
                            "is_capital": (city_item.get("Iscapital") or "False") == "True",
                        })
            return {"success": True, "cities": cities}
        except Exception as e:
            logger.error("list_of_cities_error", error=str(e), country=country, exc_info=True)
            return {"success": False, "error_message": str(e), "cities": []}

    async def list_of_retail_cities(self, country: str = "SA") -> Dict[str, Any]:
        """Get list of retail cities by country code."""
        soap_action = "https://mobileapi.smsaexpress.com/smsamobilepro/ListOfRetailCities"
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <ListOfRetailCities xmlns="https://mobileapi.smsaexpress.com/smsamobilepro/">
      <country>{country}</country>
      <language>English</language>
      <passkey>{self._passkey}</passkey>
    </ListOfRetailCities>
  </soap:Body>
</soap:Envelope>"""
        try:
            xml_text = await self._post_soap(soap_action, envelope)
            parsed = xmltodict.parse(xml_text)
            body = parsed.get("soap:Envelope", {}).get("soap:Body", {})
            response = body.get("ListOfRetailCitiesResponse", {}).get("ListOfRetailCitiesResult", {})
            cities = []
            if isinstance(response, dict):
                city_list = response.get("Rcity", [])
                if not isinstance(city_list, list):
                    city_list = [city_list] if city_list else []
                
                for city_item in city_list:
                    if isinstance(city_item, dict):
                        city_name = city_item.get("City")
                        if city_name:
                            cities.append({"name": str(city_name)})
            return {"success": True, "cities": cities}
        except Exception as e:
            logger.error("list_of_retail_cities_error", error=str(e), country=country, exc_info=True)
            return {"success": False, "error_message": str(e), "cities": []}

    def _parse_working_hours(self, center_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse working hours from center data.
        Returns dict with day names as keys and list of shifts as values.
        """
        days = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]
        working_hours = {}
        
        for day in days:
            shifts = []
            # Check for shift 1 - handle None values
            shift1_from_val = center_data.get(f"{day}Shift1From") or ""
            shift1_to_val = center_data.get(f"{day}Shift1To") or ""
            shift1_from = str(shift1_from_val).strip() if shift1_from_val is not None else ""
            shift1_to = str(shift1_to_val).strip() if shift1_to_val is not None else ""
            if shift1_from and shift1_to:
                shifts.append(f"{shift1_from}-{shift1_to}")
            
            # Check for shift 2 - handle None values
            shift2_from_val = center_data.get(f"{day}Shift2From") or ""
            shift2_to_val = center_data.get(f"{day}Shift2To") or ""
            shift2_from = str(shift2_from_val).strip() if shift2_from_val is not None else ""
            shift2_to = str(shift2_to_val).strip() if shift2_to_val is not None else ""
            if shift2_from and shift2_to:
                shifts.append(f"{shift2_from}-{shift2_to}")
            
            if shifts:
                working_hours[day] = shifts
            else:
                working_hours[day] = []  # Closed or no shifts
        
        return working_hours

    async def list_of_centers(
        self,
        city: Optional[str] = None,
        country: str = "SA",
    ) -> Dict[str, Any]:
        """
        Get list of service centers by country and city.
        Returns centers with Lat-Long coordinates.
        """
        soap_action = "https://mobileapi.smsaexpress.com/smsamobilepro/ListOfCenters"
        city_xml = f"<city>{city}</city>" if city else ""
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <ListOfCenters xmlns="https://mobileapi.smsaexpress.com/smsamobilepro/">
      <country>{country}</country>
      {city_xml}
      <language>English</language>
      <passkey>{self._passkey}</passkey>
    </ListOfCenters>
  </soap:Body>
</soap:Envelope>"""
        try:
            xml_text = await self._post_soap(soap_action, envelope)
            parsed = xmltodict.parse(xml_text)
            body = parsed.get("soap:Envelope", {}).get("soap:Body", {})
            response = body.get("ListOfCentersResponse", {}).get("ListOfCentersResult", {})
            
            centers = []
            if isinstance(response, dict):
                center_list = response.get("RetailRes", [])
                if not isinstance(center_list, list):
                    center_list = [center_list] if center_list else []
                
                for center_data in center_list:
                    if isinstance(center_data, dict):
                        # Extract coordinates (critical for distance calculation)
                        # Handle None values properly
                        lat_val = center_data.get("GPSCoordinateLatitude") or ""
                        lng_val = center_data.get("GPSCoordinateLongitude") or ""
                        lat_str = str(lat_val).strip() if lat_val is not None else ""
                        lng_str = str(lng_val).strip() if lng_val is not None else ""
                        
                        latitude = None
                        longitude = None
                        try:
                            if lat_str:
                                latitude = float(lat_str)
                            if lng_str:
                                longitude = float(lng_str)
                        except (ValueError, TypeError):
                            pass
                        
                        # Parse working hours
                        working_hours = self._parse_working_hours(center_data)
                        
                        # Extract address (use Address1En) - handle None
                        address_val = center_data.get("Address1En") or ""
                        address = str(address_val).strip() if address_val is not None else ""
                        
                        # Generate center name from address or use city
                        # Address format: "KSA 41112 - RUH Sultanah Swaidi St."
                        # Try to extract area/street name for better naming
                        city_val = center_data.get("City") or "Service Center"
                        city_name = str(city_val) if city_val is not None else "Service Center"
                        center_name = f"SMSA {city_name} Branch"
                        if address and address != "N/A":
                            # Try to extract area name from address (after "RUH" or similar patterns)
                            address_parts = address.split(" - ")
                            if len(address_parts) > 1:
                                area_part = address_parts[1].split(" St.")[0].split(" Rd.")[0]
                                if area_part and len(area_part) > 3:
                                    center_name = f"SMSA {area_part} Branch"
                        
                        # Helper function to safely get and strip string values
                        def safe_get_str(key: str, default: str = "N/A") -> str:
                            val = center_data.get(key)
                            if val is None:
                                return default
                            return str(val).strip() or default
                        
                        centers.append({
                            "code": safe_get_str("Retailcode", "N/A"),
                            "name": center_name,
                            "address": address or "N/A",
                            "city": safe_get_str("City", city or "N/A"),
                            "country": safe_get_str("Country", "N/A"),
                            "region": safe_get_str("Region", "N/A"),
                            "phone": safe_get_str("Phone", "N/A"),
                            "latitude": latitude,
                            "longitude": longitude,
                            "working_hours": working_hours,
                            "cold_box": (center_data.get("ColdBox") or "N") == "Y",
                            "short_code": safe_get_str("ShortCode", "N/A"),
                        })
            
            return {
                "success": True,
                "centers": centers,
                "count": len(centers),
            }

        except aiohttp.ClientResponseError as e:
            logger.error(
                "retail_centers_api_error",
                status=e.status,
                message=e.message,
                city=city,
                country=country,
            )
            return {
                "success": False,
                "error_code": "API_ERROR",
                "error_message": f"SMSA retail centers API returned error {e.status}: {e.message}",
                "centers": [],
            }
        except aiohttp.ClientError as e:
            logger.error(
                "retail_centers_network_error",
                error=str(e),
                city=city,
                country=country,
            )
            return {
                "success": False,
                "error_code": "NETWORK_ERROR",
                "error_message": f"Failed to connect to SMSA retail centers API: {e}",
                "centers": [],
            }
        except Exception as e:
            logger.error(
                "retail_centers_unexpected_error",
                error=str(e),
                city=city,
                country=country,
                exc_info=True,
            )
            return {
                "success": False,
                "error_code": "API_ERROR",
                "error_message": f"SMSA retail centers API error: {e}",
                "centers": [],
            }

    async def service_center_by_code(self, code: str) -> Dict[str, Any]:
        """Get service center details by code."""
        soap_action = "https://mobileapi.smsaexpress.com/smsamobilepro/ServiceCenterByCode"
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <ServiceCenterByCode xmlns="https://mobileapi.smsaexpress.com/smsamobilepro/">
      <code>{code}</code>
      <language>English</language>
      <passkey>{self._passkey}</passkey>
    </ServiceCenterByCode>
  </soap:Body>
</soap:Envelope>"""
        try:
            xml_text = await self._post_soap(soap_action, envelope)
            parsed = xmltodict.parse(xml_text)
            body = parsed.get("soap:Envelope", {}).get("soap:Body", {})
            response = body.get("ServiceCenterByCodeResponse", {}).get("ServiceCenterByCodeResult", {})
            
            if isinstance(response, dict):
                center_data = response.get("RetailRes", {})
                if isinstance(center_data, dict):
                    # Extract coordinates - handle None values
                    lat_val = center_data.get("GPSCoordinateLatitude") or ""
                    lng_val = center_data.get("GPSCoordinateLongitude") or ""
                    lat_str = str(lat_val).strip() if lat_val is not None else ""
                    lng_str = str(lng_val).strip() if lng_val is not None else ""
                    
                    latitude = None
                    longitude = None
                    try:
                        if lat_str:
                            latitude = float(lat_str)
                        if lng_str:
                            longitude = float(lng_str)
                    except (ValueError, TypeError):
                        pass
                    
                    # Parse working hours
                    working_hours = self._parse_working_hours(center_data)
                    
                    # Extract address - handle None
                    address_val = center_data.get("Address1En") or ""
                    address = str(address_val).strip() if address_val is not None else ""
                    
                    # Generate center name from address or use city
                    city_val = center_data.get("City") or "Service Center"
                    city_name = str(city_val) if city_val is not None else "Service Center"
                    center_name = f"SMSA {city_name} Branch"
                    if address and address != "N/A":
                        # Try to extract area name from address
                        address_parts = address.split(" - ")
                        if len(address_parts) > 1:
                            area_part = address_parts[1].split(" St.")[0].split(" Rd.")[0]
                            if area_part and len(area_part) > 3:
                                center_name = f"SMSA {area_part} Branch"
                    
                    # Helper function to safely get and strip string values
                    def safe_get_str(key: str, default: str = "N/A") -> str:
                        val = center_data.get(key)
                        if val is None:
                            return default
                        return str(val).strip() or default
                    
                    center = {
                        "code": safe_get_str("Retailcode", code),
                        "name": center_name,
                        "address": address or "N/A",
                        "city": safe_get_str("City", "N/A"),
                        "country": safe_get_str("Country", "N/A"),
                        "region": safe_get_str("Region", "N/A"),
                        "phone": safe_get_str("Phone", "N/A"),
                        "latitude": latitude,
                        "longitude": longitude,
                        "working_hours": working_hours,
                        "cold_box": (center_data.get("ColdBox") or "N") == "Y",
                        "short_code": safe_get_str("ShortCode", "N/A"),
                    }
                    return {"success": True, "center": center}
            return {"success": False, "error_message": "Invalid response format", "center": None}
        except Exception as e:
            logger.error("service_center_by_code_error", error=str(e), code=code, exc_info=True)
            return {"success": False, "error_message": str(e), "center": None}

    # Backward compatibility method
    async def get_retail_centers(
        self,
        city: Optional[str] = None,
        country: str = "SA",
    ) -> Dict[str, Any]:
        """Backward compatibility wrapper for list_of_centers."""
        return await self.list_of_centers(city=city, country=country)
