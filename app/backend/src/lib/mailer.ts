import nodemailer from "nodemailer";
import { env } from "../config/env";

// Transactional email (verification + password reset). With SMTP_URL set
// (e.g. smtp://localhost:1026 for the Mailpit container in
// docker-compose.yml) mail is really sent; without it the message is
// printed to the console so local dev works with zero setup.
const transport = env.smtpUrl ? nodemailer.createTransport(env.smtpUrl) : null;

export type Mail = { to: string; subject: string; text: string };

export async function sendMail(mail: Mail) {
  if (!transport) {
    console.log(`[mail] to=${mail.to} subject="${mail.subject}"\n${mail.text}\n`);
    return;
  }
  await transport.sendMail({ from: env.mailFrom, ...mail });
}
