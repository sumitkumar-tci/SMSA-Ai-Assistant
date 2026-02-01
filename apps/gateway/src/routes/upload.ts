import express, { Request, Response } from "express";
import multer from "multer";
import FormData from "form-data";
import axios from "axios";
import { logger } from "../logger";

export const router = express.Router();

// Configure multer for file uploads (memory storage)
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 10 * 1024 * 1024, // 10MB limit
  },
});

router.post("/upload", upload.single("file"), async (req: Request, res: Response) => {
  try {
    const conversationId = req.body?.conversationId || req.query?.conversationId;

    // Check if file is in request
    if (!req.file) {
      return res.status(400).json({
        success: false,
        error: "No file provided. Please upload a file using multipart/form-data with field name 'file'.",
      });
    }

    const file = req.file;

    // Create form data to forward to AI engine
    const formData = new FormData();
    formData.append("file", file.buffer, {
      filename: file.originalname || "uploaded_file",
      contentType: file.mimetype || "application/octet-stream",
    });

    if (conversationId) {
      formData.append("conversation_id", conversationId);
    }

    // Forward to AI engine
    const aiEngineUrl = process.env.AI_ENGINE_URL || "http://localhost:8000";
    const response = await axios.post(`${aiEngineUrl}/upload`, formData, {
      headers: {
        ...formData.getHeaders(),
      },
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
    });

    logger.info("file_upload_proxied", {
      conversation_id: conversationId,
      object_key: response.data.object_key,
    });

    return res.json(response.data);
  } catch (error: any) {
    logger.error("file_upload_error", { error: error.message });
    return res.status(500).json({
      success: false,
      error: error.message || "Failed to upload file",
    });
  }
});
