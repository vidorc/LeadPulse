import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "../services/api";

export default function LeadDetails() {
  const { id } = useParams();
  const [events, setEvents] = useState([]);

  useEffect(() => {
    api.get(`/leads/events/${id}`).then((res) => {
      setEvents(res.data);
    });
  }, [id]);

  return (
    <div className="page">
      <h1>Lead Timeline</h1>

      {events.map((event) => (
        <div className="card" key={event.id}>
          <h3>{event.event_type}</h3>
          <p>{event.details}</p>
        </div>
      ))}
    </div>
  );
}