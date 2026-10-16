
"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { api, ApiError } from "@/lib/api";


type FormValues = {
  email: string;
  password: string;
  confirmPassword: string;
};

type FormErrors = Partial<
  Record<keyof FormValues, string>
>;


const initialValues: FormValues = {
  email: "",
  password: "",
  confirmPassword: "",
};


function validateForm(values: FormValues): FormErrors {
  const errors: FormErrors = {};

  const email = values.email.trim();

  if (!email) {
    errors.email = "Email is required.";
  } else if (
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  ) {
    errors.email = "Enter a valid email address.";
  }

  if (!values.password) {
    errors.password = "Password is required.";
  } else if (values.password.length < 8) {
    errors.password = "Use at least 8 characters.";
  } else if (values.password.length > 128) {
    errors.password = "Use at most 128 characters.";
  } else if (
    new TextEncoder().encode(values.password).length > 256
  ) {
    errors.password = "Password exceeds 256 UTF-8 bytes.";
  } else if (!values.password.trim()) {
    errors.password = "Password cannot be only whitespace.";
  }

  if (!values.confirmPassword) {
    errors.confirmPassword = "Confirm your password.";
  } else if (
    values.confirmPassword !== values.password
  ) {
    errors.confirmPassword = "Passwords do not match.";
  }

  return errors;
}


export default function RegisterPage() {
  const [values, setValues] =
    useState<FormValues>(initialValues);

  const [errors, setErrors] =
    useState<FormErrors>({});

  const [serverError, setServerError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registeredEmail, setRegisteredEmail] =
    useState<string | null>(null);

  function updateField(
    field: keyof FormValues,
    value: string
  ) {
    setValues((previous) => ({
      ...previous,
      [field]: value,
    }));

    setErrors((previous) => ({
      ...previous,
      [field]: undefined,
    }));

    setServerError("");
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (isSubmitting) return;

    const validationErrors = validateForm(values);

    setErrors(validationErrors);
    setServerError("");

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    setIsSubmitting(true);

    try {
      const user = await api.register({
        email: values.email.trim().toLowerCase(),
        password: values.password,
      });

      setRegisteredEmail(user.email);

      setValues(initialValues);
      setErrors({});
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 409) {
          setErrors({
            email: "This email is already registered.",
          });
        } else {
          setServerError(error.message);
        }
      } else {
        setServerError(
          "Unable to connect to the server. Please try again."
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (registeredEmail) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12 text-slate-900">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-2xl text-green-700">
            ✓
          </div>

          <h1 className="text-2xl font-bold">
            Account created
          </h1>

          <p className="mt-3 text-sm leading-6 text-slate-600">
            Your File Vault account has been created
            for{" "}
            <span className="font-medium text-slate-900">
              {registeredEmail}
            </span>
            .
          </p>

          <p className="mt-2 text-sm text-slate-600">
            Sign in to start uploading your files.
          </p>

          <Link
            href="/login"
            className="mt-6 block rounded-lg bg-slate-900 px-4 py-3 text-center text-sm font-semibold text-white hover:bg-slate-800"
          >
            Continue to login
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12 text-slate-900">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <Link
            href="/"
            className="text-sm font-semibold text-slate-600 hover:text-slate-900"
          >
            File Vault
          </Link>

          <h1 className="mt-4 text-3xl font-bold tracking-tight">
            Create your account
          </h1>

          <p className="mt-2 text-sm text-slate-600">
            Securely store and manage your files.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="space-y-5 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm"
        >
          <div>
            <label
              htmlFor="email"
              className="mb-2 block text-sm font-medium"
            >
              Email address
            </label>

            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              value={values.email}
              onChange={(event) =>
                updateField("email", event.target.value)
              }
              aria-invalid={Boolean(errors.email)}
              aria-describedby={
                errors.email ? "email-error" : undefined
              }
              disabled={isSubmitting}
              placeholder="you@example.com"
              className="w-full rounded-lg border border-slate-300 px-3 py-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
            />

            {errors.email && (
              <p
                id="email-error"
                role="alert"
                className="mt-2 text-sm text-red-600"
              >
                {errors.email}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-2 block text-sm font-medium"
            >
              Password
            </label>

            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              value={values.password}
              onChange={(event) =>
                updateField("password", event.target.value)
              }
              aria-invalid={Boolean(errors.password)}
              aria-describedby={
                errors.password ? "password-error" : undefined
              }
              disabled={isSubmitting}
              placeholder="At least 8 characters"
              className="w-full rounded-lg border border-slate-300 px-3 py-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
            />

            {errors.password && (
              <p
                id="password-error"
                role="alert"
                className="mt-2 text-sm text-red-600"
              >
                {errors.password}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="mb-2 block text-sm font-medium"
            >
              Confirm password
            </label>

            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={values.confirmPassword}
              onChange={(event) =>
                updateField(
                  "confirmPassword",
                  event.target.value
                )
              }
              aria-invalid={Boolean(
                errors.confirmPassword
              )}
              aria-describedby={
                errors.confirmPassword
                  ? "confirm-password-error"
                  : undefined
              }
              disabled={isSubmitting}
              placeholder="Re-enter your password"
              className="w-full rounded-lg border border-slate-300 px-3 py-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
            />

            {errors.confirmPassword && (
              <p
                id="confirm-password-error"
                role="alert"
                className="mt-2 text-sm text-red-600"
              >
                {errors.confirmPassword}
              </p>
            )}
          </div>

          {serverError && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              {serverError}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting
              ? "Creating account..."
              : "Create account"}
          </button>

          <p className="text-center text-sm text-slate-600">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-semibold text-slate-900 underline underline-offset-4"
            >
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
