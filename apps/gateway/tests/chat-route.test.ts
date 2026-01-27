import request from "supertest";
import express from "express";
import { router } from "../src/routes/chat";

const app = express();
app.use(express.json());
app.use("/api", router);

describe("chat route", () => {
  it("responds to tracking stream request", async () => {
    // This is a very light smoke test; in a real suite we'd mock openTrackingStream.
    const res = await request(app)
      .post("/api/messages/test-conv/stream")
      .send({ message: "track 227047923763" });

    expect(res.status).toBe(200);
  });
});

