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


class SMSATrackingClientConfig(BaseModel):
    username: str
    password: str
    base_url: str


class SMSATrackingClient:
    """
    Async client for SMSA Tracking SOAP API using the credentials and payload
    structure provided in the project reference.
    """

    def __init__(self, config: Optional[SMSATrackingClientConfig] = None) -> None:
        if config is None:
            config = SMSATrackingClientConfig(
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


class SMSARatesClient:
    """
    Async client for SMSA Rates Inquiry REST API.

    Endpoint: POST https://mobileapi.smsaexpress.com/SmsaMobileWebServiceRestApi/api/RateInquiry/inquiry
    Headers: Content-Type: application/json, Passkey: riai$ervice
    """

    def __init__(self) -> None:
        self._base_url = settings.smsa_rates_base_url
        self._passkey = settings.smsa_rates_passkey
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
        pieces: str,
        service_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get shipping rates from SMSA Rates API.

        Args:
            from_country: Origin country code (e.g., "SA")
            to_country: Destination country code (e.g., "SA")
            origin_city: Origin city name (e.g., "Riyadh")
            destination_city: Destination city name (e.g., "Jeddah")
            weight: Weight as string (e.g., "5")
            pieces: Number of pieces as string (e.g., "1")
            service_type: Optional service type (e.g., "DLV")

        Returns:
            Dict with success, rates data, and error info if any.
        """
        from ..models.rates import RateInquiryRequest, RateInquiryResponse, RateResult

        session = await self._get_session()

        # Build request payload - all fields as strings
        payload = {
            "FromCountry": from_country,
            "ToCountry": to_country,
            "OriginCity": origin_city,
            "DestinationCity": destination_city,
            "Weight": weight,  # Must be string, not number
            "Pieces": pieces,  # Must be string, not number
        }
        if service_type:
            payload["ServiceType"] = service_type

        headers = {
            "Content-Type": "application/json",
            "Passkey": self._passkey,
        }

        try:
            async with session.post(
                self._base_url, json=payload, headers=headers
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return RateResult(
                        success=False,
                        error_code="HTTP_ERROR",
                        error_message=f"SMSA rates API error {resp.status}: {text[:200]}",
                    ).model_dump(by_alias=True)

                json_data = await resp.json()

                # Parse response using Pydantic model
                api_response = RateInquiryResponse(**json_data)

                # Convert to agent-friendly format
                rates = []
                for rate_option in api_response.data:
                    rates.append(
                        {
                            "service": rate_option.service_type,
                            "serviceName": rate_option.service_name,
                            "amount": rate_option.charge,
                            "currency": rate_option.currency,
                            "eta": rate_option.estimated_days or "N/A",
                        }
                    )

                return RateResult(
                    success=api_response.success,
                    rates=rates,
                ).model_dump(by_alias=True)

        except aiohttp.ClientError as e:
            return RateResult(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=f"Failed to connect to SMSA rates API: {e}",
            ).model_dump(by_alias=True)
        except Exception as e:
            return RateResult(
                success=False,
                error_code="PARSE_ERROR",
                error_message=f"Failed to parse SMSA rates response: {e}",
            ).model_dump(by_alias=True)

