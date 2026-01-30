#!/usr/bin/env node

// Simple MCP-style travel server with mock flight data.
// Follows the same JSON-RPC + tools/list + tools/call protocol
// as blinkit-server.js and payment-server.js.

import * as readline from "node:readline";

// Debug: log to stderr so it doesn't interfere with JSON-RPC on stdout
console.error("[travel-server] starting up...");

// --- Mock data ----------------------------------------------------------------

// Basic set of mock flights. In a real system this would be backed by an API.
// We include multiple options for common Indian leisure routes (Mumbai, Goa, Delhi, Bangalore).
const MOCK_FLIGHTS = [
  // Delhi ⇄ Bangalore
  {
    flightId: "TRV-001",
    airline: "Cursor Air",
    origin: "DEL",
    destination: "BLR",
    date: "2026-02-01",
    departureTime: "2026-02-01T09:30:00+05:30",
    arrivalTime: "2026-02-01T12:10:00+05:30",
    durationMinutes: 160,
    cabin: "economy",
    price: 6500,
    currency: "INR",
  },
  {
    flightId: "TRV-002",
    airline: "Cursor Air",
    origin: "DEL",
    destination: "BLR",
    date: "2026-02-01",
    departureTime: "2026-02-01T18:00:00+05:30",
    arrivalTime: "2026-02-01T20:30:00+05:30",
    durationMinutes: 150,
    cabin: "economy",
    price: 7200,
    currency: "INR",
  },
  {
    flightId: "TRV-005",
    airline: "NP Travel",
    origin: "BLR",
    destination: "DEL",
    date: "2026-02-05",
    departureTime: "2026-02-05T07:15:00+05:30",
    arrivalTime: "2026-02-05T09:45:00+05:30",
    durationMinutes: 150,
    cabin: "economy",
    price: 6400,
    currency: "INR",
  },
  {
    flightId: "TRV-006",
    airline: "NP Travel",
    origin: "BLR",
    destination: "DEL",
    date: "2026-02-05",
    departureTime: "2026-02-05T20:10:00+05:30",
    arrivalTime: "2026-02-05T22:40:00+05:30",
    durationMinutes: 150,
    cabin: "economy",
    price: 6900,
    currency: "INR",
  },

  // Mumbai ⇄ Goa
  {
    flightId: "TRV-003",
    airline: "NP Travel",
    origin: "BOM",
    destination: "GOA",
    date: "2026-02-10",
    departureTime: "2026-02-10T07:00:00+05:30",
    arrivalTime: "2026-02-10T08:10:00+05:30",
    durationMinutes: 70,
    cabin: "economy",
    price: 4800,
    currency: "INR",
  },
  {
    flightId: "TRV-007",
    airline: "Cursor Air",
    origin: "BOM",
    destination: "GOA",
    date: "2026-02-10",
    departureTime: "2026-02-10T13:30:00+05:30",
    arrivalTime: "2026-02-10T14:40:00+05:30",
    durationMinutes: 70,
    cabin: "economy",
    price: 5100,
    currency: "INR",
  },
  {
    flightId: "TRV-008",
    airline: "NP Travel",
    origin: "GOA",
    destination: "BOM",
    date: "2026-02-15",
    departureTime: "2026-02-15T10:00:00+05:30",
    arrivalTime: "2026-02-15T11:10:00+05:30",
    durationMinutes: 70,
    cabin: "economy",
    price: 4950,
    currency: "INR",
  },
  {
    flightId: "TRV-009",
    airline: "Cursor Air",
    origin: "GOA",
    destination: "BOM",
    date: "2026-02-15",
    departureTime: "2026-02-15T19:20:00+05:30",
    arrivalTime: "2026-02-15T20:30:00+05:30",
    durationMinutes: 70,
    cabin: "economy",
    price: 5300,
    currency: "INR",
  },

  // Delhi ⇄ Goa (via direct mock flights)
  {
    flightId: "TRV-010",
    airline: "Cursor Air",
    origin: "DEL",
    destination: "GOA",
    date: "2026-03-01",
    departureTime: "2026-03-01T06:30:00+05:30",
    arrivalTime: "2026-03-01T09:10:00+05:30",
    durationMinutes: 160,
    cabin: "economy",
    price: 7800,
    currency: "INR",
  },
  {
    flightId: "TRV-011",
    airline: "NP Travel",
    origin: "DEL",
    destination: "GOA",
    date: "2026-03-01",
    departureTime: "2026-03-01T15:00:00+05:30",
    arrivalTime: "2026-03-01T17:40:00+05:30",
    durationMinutes: 160,
    cabin: "economy",
    price: 8200,
    currency: "INR",
  },
  {
    flightId: "TRV-012",
    airline: "Cursor Air",
    origin: "GOA",
    destination: "DEL",
    date: "2026-03-05",
    departureTime: "2026-03-05T09:20:00+05:30",
    arrivalTime: "2026-03-05T12:00:00+05:30",
    durationMinutes: 160,
    cabin: "economy",
    price: 7750,
    currency: "INR",
  },
  {
    flightId: "TRV-013",
    airline: "NP Travel",
    origin: "GOA",
    destination: "DEL",
    date: "2026-03-05",
    departureTime: "2026-03-05T21:10:00+05:30",
    arrivalTime: "2026-03-06T00:00:00+05:30",
    durationMinutes: 170,
    cabin: "economy",
    price: 8300,
    currency: "INR",
  },

  // Bangalore ⇄ Goa (existing + extra)
  {
    flightId: "TRV-004",
    airline: "NP Travel",
    origin: "BLR",
    destination: "GOA",
    date: "2026-03-01",
    departureTime: "2026-03-01T10:15:00+05:30",
    arrivalTime: "2026-03-01T11:45:00+05:30",
    durationMinutes: 90,
    cabin: "economy",
    price: 5200,
    currency: "INR",
  },
  {
    flightId: "TRV-014",
    airline: "Cursor Air",
    origin: "BLR",
    destination: "GOA",
    date: "2026-03-01",
    departureTime: "2026-03-01T17:30:00+05:30",
    arrivalTime: "2026-03-01T19:00:00+05:30",
    durationMinutes: 90,
    cabin: "economy",
    price: 5400,
    currency: "INR",
  },
  {
    flightId: "TRV-015",
    airline: "NP Travel",
    origin: "GOA",
    destination: "BLR",
    date: "2026-03-05",
    departureTime: "2026-03-05T08:40:00+05:30",
    arrivalTime: "2026-03-05T10:10:00+05:30",
    durationMinutes: 90,
    cabin: "economy",
    price: 5150,
    currency: "INR",
  },
  {
    flightId: "TRV-016",
    airline: "Cursor Air",
    origin: "GOA",
    destination: "BLR",
    date: "2026-03-05",
    departureTime: "2026-03-05T20:00:00+05:30",
    arrivalTime: "2026-03-05T21:30:00+05:30",
    durationMinutes: 90,
    cabin: "economy",
    price: 5550,
    currency: "INR",
  },
  // Extra variety for popular metro routes (Delhi ⇄ Mumbai, Mumbai ⇄ Bangalore)
  {
    flightId: "TRV-017",
    airline: "MetroJet",
    origin: "DEL",
    destination: "BOM",
    date: "2026-02-20",
    departureTime: "2026-02-20T06:45:00+05:30",
    arrivalTime: "2026-02-20T09:00:00+05:30",
    durationMinutes: 135,
    cabin: "economy",
    price: 7100,
    currency: "INR",
  },
  {
    flightId: "TRV-018",
    airline: "MetroJet",
    origin: "DEL",
    destination: "BOM",
    date: "2026-02-20",
    departureTime: "2026-02-20T19:15:00+05:30",
    arrivalTime: "2026-02-20T21:35:00+05:30",
    durationMinutes: 140,
    cabin: "economy",
    price: 7650,
    currency: "INR",
  },
  {
    flightId: "TRV-019",
    airline: "MetroJet",
    origin: "BOM",
    destination: "DEL",
    date: "2026-02-24",
    departureTime: "2026-02-24T08:20:00+05:30",
    arrivalTime: "2026-02-24T10:35:00+05:30",
    durationMinutes: 135,
    cabin: "economy",
    price: 7250,
    currency: "INR",
  },
  {
    flightId: "TRV-020",
    airline: "MetroJet",
    origin: "BOM",
    destination: "DEL",
    date: "2026-02-24",
    departureTime: "2026-02-24T21:10:00+05:30",
    arrivalTime: "2026-02-24T23:25:00+05:30",
    durationMinutes: 135,
    cabin: "economy",
    price: 7800,
    currency: "INR",
  },
  {
    flightId: "TRV-021",
    airline: "MetroJet",
    origin: "BOM",
    destination: "BLR",
    date: "2026-03-10",
    departureTime: "2026-03-10T07:10:00+05:30",
    arrivalTime: "2026-03-10T08:40:00+05:30",
    durationMinutes: 90,
    cabin: "economy",
    price: 6200,
    currency: "INR",
  },
  {
    flightId: "TRV-022",
    airline: "MetroJet",
    origin: "BOM",
    destination: "BLR",
    date: "2026-03-10",
    departureTime: "2026-03-10T18:30:00+05:30",
    arrivalTime: "2026-03-10T20:05:00+05:30",
    durationMinutes: 95,
    cabin: "economy",
    price: 6600,
    currency: "INR",
  },
  {
    flightId: "TRV-023",
    airline: "MetroJet",
    origin: "BLR",
    destination: "BOM",
    date: "2026-03-14",
    departureTime: "2026-03-14T09:55:00+05:30",
    arrivalTime: "2026-03-14T11:30:00+05:30",
    durationMinutes: 95,
    cabin: "economy",
    price: 6350,
    currency: "INR",
  },
  {
    flightId: "TRV-024",
    airline: "MetroJet",
    origin: "BLR",
    destination: "BOM",
    date: "2026-03-14",
    departureTime: "2026-03-14T20:15:00+05:30",
    arrivalTime: "2026-03-14T21:50:00+05:30",
    durationMinutes: 95,
    cabin: "economy",
    price: 6850,
    currency: "INR",
  },
];

// Simple in-memory booking store
const BOOKINGS = new Map(); // bookingId -> booking object

// --- Mock hotels (Mumbai, Goa, Delhi, Bangalore) ---------------------------------
const MOCK_HOTELS = [
  { hotelId: "HTL-001", name: "Sea View Resort", city: "GOA", address: "Calangute Beach", pricePerNight: 4500, currency: "INR", rating: 4.5, amenities: ["WiFi", "Pool", "Beach access"], maxGuests: 4 },
  { hotelId: "HTL-002", name: "Goa Heritage Inn", city: "GOA", address: "Panjim", pricePerNight: 2800, currency: "INR", rating: 4.2, amenities: ["WiFi", "Breakfast"], maxGuests: 3 },
  { hotelId: "HTL-003", name: "Sunset Lodge Goa", city: "GOA", address: "Baga", pricePerNight: 5200, currency: "INR", rating: 4.6, amenities: ["WiFi", "Pool", "Restaurant"], maxGuests: 4 },
  { hotelId: "HTL-004", name: "Gateway Grand Mumbai", city: "BOM", address: "Colaba", pricePerNight: 6500, currency: "INR", rating: 4.4, amenities: ["WiFi", "Gym", "Restaurant"], maxGuests: 3 },
  { hotelId: "HTL-005", name: "Mumbai Central Stay", city: "BOM", address: "Andheri", pricePerNight: 3200, currency: "INR", rating: 4.0, amenities: ["WiFi", "Breakfast"], maxGuests: 2 },
  { hotelId: "HTL-006", name: "Marine Plaza Mumbai", city: "BOM", address: "Marine Drive", pricePerNight: 7800, currency: "INR", rating: 4.7, amenities: ["WiFi", "Pool", "Spa", "Restaurant"], maxGuests: 4 },
  { hotelId: "HTL-007", name: "Capital Inn Delhi", city: "DEL", address: "Connaught Place", pricePerNight: 4200, currency: "INR", rating: 4.3, amenities: ["WiFi", "Breakfast", "Gym"], maxGuests: 3 },
  { hotelId: "HTL-008", name: "Delhi Heritage Hotel", city: "DEL", address: "Paharganj", pricePerNight: 2200, currency: "INR", rating: 3.8, amenities: ["WiFi"], maxGuests: 2 },
  { hotelId: "HTL-009", name: "The Grand Delhi", city: "DEL", address: "Aerocity", pricePerNight: 9500, currency: "INR", rating: 4.8, amenities: ["WiFi", "Pool", "Spa", "Restaurant", "Airport shuttle"], maxGuests: 4 },
  { hotelId: "HTL-010", name: "Bangalore Tech Hub Hotel", city: "BLR", address: "Koramangala", pricePerNight: 3800, currency: "INR", rating: 4.2, amenities: ["WiFi", "Gym", "Breakfast"], maxGuests: 3 },
  { hotelId: "HTL-011", name: "Garden City Inn", city: "BLR", address: "Indiranagar", pricePerNight: 4500, currency: "INR", rating: 4.4, amenities: ["WiFi", "Restaurant", "Garden"], maxGuests: 4 },
  { hotelId: "HTL-012", name: "Luxury Suites Bangalore", city: "BLR", address: "MG Road", pricePerNight: 7200, currency: "INR", rating: 4.6, amenities: ["WiFi", "Pool", "Spa", "Restaurant"], maxGuests: 4 },
];

const HOTEL_BOOKINGS = new Map(); // hotelBookingId -> booking object

function normalizeCode(value) {
  if (!value) return "";
  const code = String(value).trim().toUpperCase();
  // Allow common user variants and map them to our dummy data city/airport codes
  if (code === "GOI" || code === "GOA" || code === "goa" || code === "Goa") return "GOA";         // Goa airport code -> city code used in MOCK_FLIGHTS
  if (code === "MUMBAI" || code === "BOMBAY" || code === "MUM" || code === "BOM" || code === "mumbai" || code === "bombay" || code === "mum" || code === "bom" || code === "Mumbai" || code === "Bombay" || code === "Mum" || code === "Bom") return "BOM";
  if (code === "BANGALORE" || code === "BENGALURU" || code === "BLR" || code === "bangalore" || code === "bengaluru" || code === "blr" || code === "Bangalore" || code === "Bengaluru" || code === "Blr" || code === "Bangalore" || code === "Bengaluru" || code === "Blr") return "BLR";
  if (code === "DELHI" || code === "NEW DELHI" || code === "NDLS" || code === "DEL" || code === "delhi" || code === "new delhi" || code === "ndls" || code === "del" || code === "Delhi" || code === "New Delhi" || code === "Ndls" || code === "Del" || code === "Delhi" || code === "New Delhi" || code === "Ndls" || code === "Del") return "DEL";

  return code;
}

function normalizeDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10); // YYYY-MM-DD
}

function findFlights(params) {
  const origin = normalizeCode(params.origin);
  const destination = normalizeCode(params.destination);
  const date = normalizeDate(params.date);

  // Treat MOCK_FLIGHTS as route templates and make them available for any date.
  // If a date is provided, we override the date/departure/arrival dates in the result,
  // keeping the same local times.
  const matches = MOCK_FLIGHTS.filter((f) => {
    if (origin && f.origin !== origin) return false;
    if (destination && f.destination !== destination) return false;
    return true;
  });

  if (!date) {
    return matches;
  }

  return matches.map((f) => {
    const newFlight = { ...f };
    newFlight.date = date;
    if (newFlight.departureTime && typeof newFlight.departureTime === "string") {
      newFlight.departureTime = `${date}${newFlight.departureTime.slice(10)}`;
    }
    if (newFlight.arrivalTime && typeof newFlight.arrivalTime === "string") {
      newFlight.arrivalTime = `${date}${newFlight.arrivalTime.slice(10)}`;
    }
    return newFlight;
  });
}

function getFlightById(flightId) {
  return MOCK_FLIGHTS.find((f) => f.flightId === flightId) || null;
}

function createBooking(params) {
  const { flightId, passengerName, contactEmail } = params;
  const flight = getFlightById(flightId);
  if (!flight) {
    throw new Error(`Unknown flightId: ${flightId}`);
  }

  const bookingId = `BK-${Math.random().toString(36).slice(2, 10).toUpperCase()}`;

  const booking = {
    bookingId,
    flightId: flight.flightId,
    passengerName,
    contactEmail,
    amount: flight.price,
    currency: flight.currency || "INR",
    status: "held",
    createdAt: new Date().toISOString(),
  };

  BOOKINGS.set(bookingId, booking);
  return booking;
}

function getBookingStatus(bookingId) {
  const booking = BOOKINGS.get(bookingId);
  if (!booking) {
    throw new Error(`Unknown bookingId: ${bookingId}`);
  }
  return booking;
}

function findHotels(params) {
  const city = normalizeCode(params.city);
  const checkIn = normalizeDate(params.checkIn);
  const checkOut = normalizeDate(params.checkOut);
  const guests = Math.max(1, Number(params.guests) || 1);
  const maxPrice = params.maxPricePerNight ? Number(params.maxPricePerNight) : null;

  return MOCK_HOTELS.filter((h) => {
    if (city && h.city !== city) return false;
    if (maxPrice != null && h.pricePerNight > maxPrice) return false;
    if (h.maxGuests != null && guests > h.maxGuests) return false;
    return true;
  }).map((h) => ({
    ...h,
    checkIn: checkIn || null,
    checkOut: checkOut || null,
    nights: checkIn && checkOut ? Math.max(1, Math.ceil((new Date(checkOut) - new Date(checkIn)) / (24 * 60 * 60 * 1000))) : 1,
    totalPrice: h.pricePerNight * (checkIn && checkOut ? Math.max(1, Math.ceil((new Date(checkOut) - new Date(checkIn)) / (24 * 60 * 60 * 1000))) : 1),
  }));
}

function getHotelById(hotelId) {
  return MOCK_HOTELS.find((h) => h.hotelId === hotelId) || null;
}

function createHotelBooking(params) {
  const { hotelId, guestName, contactEmail, checkIn, checkOut, guests = 1 } = params;
  const hotel = getHotelById(hotelId);
  if (!hotel) throw new Error(`Unknown hotelId: ${hotelId}`);
  const cIn = normalizeDate(checkIn);
  const cOut = normalizeDate(checkOut);
  const nights = cIn && cOut ? Math.max(1, Math.ceil((new Date(cOut) - new Date(cIn)) / (24 * 60 * 60 * 1000))) : 1;
  const amount = hotel.pricePerNight * nights;
  const bookingId = `HB-${Math.random().toString(36).slice(2, 10).toUpperCase()}`;
  const booking = {
    hotelBookingId: bookingId,
    hotelId: hotel.hotelId,
    hotelName: hotel.name,
    city: hotel.city,
    guestName,
    contactEmail,
    checkIn: cIn,
    checkOut: cOut,
    nights,
    amount,
    currency: hotel.currency || "INR",
    status: "held",
    createdAt: new Date().toISOString(),
  };
  HOTEL_BOOKINGS.set(bookingId, booking);
  return booking;
}

function getHotelBookingStatus(hotelBookingId) {
  const booking = HOTEL_BOOKINGS.get(hotelBookingId);
  if (!booking) throw new Error(`Unknown hotelBookingId: ${hotelBookingId}`);
  return booking;
}

// --- MCP tools metadata -------------------------------------------------------

const tools = [
  {
    name: "travel.search_flights",
    description: "Search mock flights between two cities on a given date",
    input_schema: {
      type: "object",
      properties: {
        origin: { type: "string", description: "Origin airport/city code (e.g., DEL, BLR)" },
        destination: { type: "string", description: "Destination airport/city code (e.g., BOM, GOA)" },
        date: { type: "string", description: "Departure date in YYYY-MM-DD format" },
      },
      required: ["origin", "destination", "date"],
    },
  },
  {
    name: "travel.get_flight",
    description: "Get detailed information for a specific mock flight",
    input_schema: {
      type: "object",
      properties: {
        flightId: { type: "string", description: "Flight ID (e.g., TRV-001)" },
      },
      required: ["flightId"],
    },
  },
  {
    name: "hold_flight_booking",
    description: "Create a held booking for a selected mock flight",
    input_schema: {
      type: "object",
      properties: {
        flightId: { type: "string", description: "Flight ID to book" },
        passengerName: { type: "string", description: "Passenger full name" },
        contactEmail: { type: "string", description: "Passenger email" },
      },
      required: ["flightId", "passengerName", "contactEmail"],
    },
  },
  {
    name: "travel.get_flight_booking_status",
    description: "Get the status of a booking by bookingId",
    input_schema: {
      type: "object",
      properties: {
        bookingId: { type: "string", description: "Booking ID returned from hold_booking" },
      },
      required: ["bookingId"],
    },
  },
  {
    name: "travel.search_hotels",
    description: "Search mock hotels by city and optional check-in/check-out dates",
    input_schema: {
      type: "object",
      properties: {
        city: { type: "string", description: "City code (e.g., GOA, BOM, DEL, BLR)" },
        checkIn: { type: "string", description: "Check-in date YYYY-MM-DD" },
        checkOut: { type: "string", description: "Check-out date YYYY-MM-DD" },
        guests: { type: "number", description: "Number of guests (default 1)" },
        maxPricePerNight: { type: "number", description: "Optional max price per night in INR" },
      },
      required: ["city"],
    },
  },
  {
    name: "travel.get_hotel",
    description: "Get detailed information for a specific hotel by hotelId",
    input_schema: {
      type: "object",
      properties: {
        hotelId: { type: "string", description: "Hotel ID (e.g., HTL-001)" },
      },
      required: ["hotelId"],
    },
  },
  {
    name: "travel.hold_hotel_booking",
    description: "Create a held booking for a selected hotel",
    input_schema: {
      type: "object",
      properties: {
        hotelId: { type: "string", description: "Hotel ID to book" },
        guestName: { type: "string", description: "Guest full name" },
        contactEmail: { type: "string", description: "Guest email" },
        checkIn: { type: "string", description: "Check-in date YYYY-MM-DD" },
        checkOut: { type: "string", description: "Check-out date YYYY-MM-DD" },
        guests: { type: "number", description: "Number of guests (default 1)" },
      },
      required: ["hotelId", "guestName", "contactEmail", "checkIn", "checkOut"],
    },
  },
  {
    name: "travel.get_hotel_booking_status",
    description: "Get the status of a hotel booking by hotelBookingId",
    input_schema: {
      type: "object",
      properties: {
        hotelBookingId: { type: "string", description: "Hotel booking ID from hold_hotel_booking" },
      },
      required: ["hotelBookingId"],
    },
  },
];

// --- JSON-RPC helpers (same shape as blinkit/payment) ------------------------

function respond(id, result) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}

function respondError(id, code, message) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n");
}

const rl = readline.createInterface({ input: process.stdin });

rl.on("line", (line) => {
  const trimmed = line.trim();
  console.error("[travel-server] received line:", trimmed);
  if (!trimmed) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch (err) {
    respondError(null, -32700, `Invalid JSON: ${err.message}`);
    return;
  }

  const { id = null, method, params = {} } = msg;
  console.error("[travel-server] parsed message:", { id, method });

  try {
    switch (method) {
      case "initialize": {
        respond(id, {
          serverInfo: { name: "travel-mcp", version: "0.1.0" },
          capabilities: { tools: { list: true, call: true } },
        });
        break;
      }
      case "tools/list": {
        respond(id, { tools });
        break;
      }
      case "tools/call": {
        const { name, arguments: args = {} } = params;
        if (!name) throw new Error("Missing tool name");

        let content;
        switch (name) {
          case "travel.search_flights": {
            const flights = findFlights(args || {});
            content = [{ type: "text", text: JSON.stringify({ flights }, null, 2) }];
            break;
          }
          case "travel.get_flight": {
            const flightId = args.flightId;
            const flight = getFlightById(flightId);
            if (!flight) throw new Error(`Unknown flightId: ${flightId}`);
            content = [{ type: "text", text: JSON.stringify({ flight }, null, 2) }];
            break;
          }
          case "hold_flight_booking": {
            const booking = createBooking(args || {});
            content = [{ type: "text", text: JSON.stringify({ booking }, null, 2) }];
            break;
          }
          case "travel.get_flight_booking_status": {
            const bookingId = args.bookingId;
            const booking = getBookingStatus(bookingId);
            content = [{ type: "text", text: JSON.stringify({ booking }, null, 2) }];
            break;
          }
          case "travel.search_hotels": {
            const hotels = findHotels(args || {});
            content = [{ type: "text", text: JSON.stringify({ hotels }, null, 2) }];
            break;
          }
          case "travel.get_hotel": {
            const hotelId = args.hotelId;
            const hotel = getHotelById(hotelId);
            if (!hotel) throw new Error(`Unknown hotelId: ${hotelId}`);
            content = [{ type: "text", text: JSON.stringify({ hotel }, null, 2) }];
            break;
          }
          case "travel.hold_hotel_booking": {
            const booking = createHotelBooking(args || {});
            content = [{ type: "text", text: JSON.stringify({ booking }, null, 2) }];
            break;
          }
          case "travel.get_hotel_booking_status": {
            const hotelBookingId = args.hotelBookingId;
            const booking = getHotelBookingStatus(hotelBookingId);
            content = [{ type: "text", text: JSON.stringify({ booking }, null, 2) }];
            break;
          }
          default:
            throw new Error(`Unknown tool: ${name}`);
        }

        respond(id, { content });
        break;
      }
      default:
        respondError(id, -32601, `Unknown method: ${method}`);
    }
  } catch (err) {
    respondError(id, -32000, err?.message ?? "Unexpected error");
  }
});

rl.on("close", () => process.exit(0));

