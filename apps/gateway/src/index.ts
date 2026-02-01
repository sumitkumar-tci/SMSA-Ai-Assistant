import express from "express";
import cors from "cors";
import helmet from "helmet";
import { router as chatRouter } from "./routes/chat";
import { router as uploadRouter } from "./routes/upload";
import { logger } from "./logger";

const app = express();

app.use(express.json());
app.use(cors());
// Configure helmet to allow SSE
app.use(
  helmet({
    contentSecurityPolicy: false, // Disable CSP for SSE
  })
);

app.use("/api", chatRouter);
app.use("/api", uploadRouter);

const port = process.env.PORT ?? 3001;

app.listen(port, () => {
  logger.info(`Gateway listening on http://localhost:${port}`);
});

