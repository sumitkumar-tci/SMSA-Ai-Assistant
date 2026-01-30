import express from "express";
import cors from "cors";
import helmet from "helmet";
import { router as chatRouter } from "./routes/chat";
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

const port = process.env.PORT ?? 3001;

app.listen(port, () => {
  logger.info(`Gateway listening on http://localhost:${port}`);
});

