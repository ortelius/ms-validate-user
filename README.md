# ortelius-ms-validate-user
Environments to Applications report microservices

![Release](https://img.shields.io/github/v/release/ortelius/ms-validate-user?sort=semver)
![license](https://img.shields.io/github/license/ortelius/.github)

![Build](https://img.shields.io/github/actions/workflow/status/ortelius/ms-validate-user/build-push-chart.yml)
[![MegaLinter](https://github.com/ortelius/ms-validate-user/workflows/MegaLinter/badge.svg?branch=main)](https://github.com/ortelius/ms-validate-user/actions?query=workflow%3AMegaLinter+branch%3Amain)
![CodeQL](https://github.com/ortelius/ms-validate-user/workflows/CodeQL/badge.svg)
[![OpenSSF
-Scorecard](https://api.securityscorecards.dev/projects/github.com/ortelius/ms-validate-user/badge)](https://api.securityscorecards.dev/projects/github.com/ortelius/ms-validate-user)

![Discord](https://img.shields.io/discord/722468819091849316)

> Version 0.1.0

ortelius-ms-validate-user

## Path Table

| Method | Path | Description |
| --- | --- | --- |
| GET | [/health](#gethealth) | Health |
| GET | [/msapi/validateuser](#getmsapivalidateuser) | Validateuser |
| GET | [/loginhelp](#getloginhelp) | Get Login Help Page |
| POST | [/forgot-username](#postforgot-username) | Forgot Username |
| POST | [/forgot-password](#postforgot-password) | Forgot Password |
| GET | [/reset-password](#getreset-password) | Get Reset Password Page |
| POST | [/reset-password](#postreset-password) | Reset Password |

## Reference Table

| Name | Path | Description |
| --- | --- | --- |
| DomainList | [#/components/schemas/DomainList](#componentsschemasdomainlist) |  |
| ForgotPasswordPayload | [#/components/schemas/ForgotPasswordPayload](#componentsschemasforgotpasswordpayload) |  |
| ForgotUsernamePayload | [#/components/schemas/ForgotUsernamePayload](#componentsschemasforgotusernamepayload) |  |
| HTTPValidationError | [#/components/schemas/HTTPValidationError](#componentsschemashttpvalidationerror) |  |
| Message | [#/components/schemas/Message](#componentsschemasmessage) |  |
| ResetPasswordPayload | [#/components/schemas/ResetPasswordPayload](#componentsschemasresetpasswordpayload) |  |
| StatusMsg | [#/components/schemas/StatusMsg](#componentsschemasstatusmsg) |  |
| ValidationError | [#/components/schemas/ValidationError](#componentsschemasvalidationerror) |  |

## Path Details

***

### [GET]/health

- Summary  
Health

- Operation id  
health_health_get

#### Responses

- 200 Successful Response

`application/json`

```typescript
{
  status?: string
  service_name?: string
}
```

***

### [GET]/msapi/validateuser

- Summary  
Validateuser

- Operation id  
validateuser_msapi_validateuser_get

#### Parameters(Query)

```typescript
domains?: Partial(string) & Partial(null)
```

#### Responses

- 200 Successful Response

`application/json`

```typescript
{
  domains?: integer[]
}
```

- 422 Validation Error

`application/json`

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

***

### [GET]/loginhelp

- Summary  
Get Login Help Page

- Operation id  
get_login_help_page_loginhelp_get

#### Responses

- 200 Successful Response

`text/html`

```typescript
{
  "type": "string"
}
```

***

### [POST]/forgot-username

- Summary  
Forgot Username

- Operation id  
forgot_username_forgot_username_post

#### RequestBody

- application/json

```typescript
{
  email: string
}
```

#### Responses

- 200 Successful Response

`application/json`

```typescript
{
  detail?: string
}
```

- 422 Validation Error

`application/json`

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

***

### [POST]/forgot-password

- Summary  
Forgot Password

- Operation id  
forgot_password_forgot_password_post

#### RequestBody

- application/json

```typescript
{
  username: string
}
```

#### Responses

- 200 Successful Response

`application/json`

```typescript
{
  detail?: string
}
```

- 422 Validation Error

`application/json`

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

***

### [GET]/reset-password

- Summary  
Get Reset Password Page

- Operation id  
get_reset_password_page_reset_password_get

#### Parameters(Query)

```typescript
token: string
```

#### Responses

- 200 Successful Response

`text/html`

```typescript
{
  "type": "string"
}
```

- 422 Validation Error

`application/json`

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

***

### [POST]/reset-password

- Summary  
Reset Password

- Operation id  
reset_password_reset_password_post

#### RequestBody

- application/json

```typescript
{
  token: string
  new_password: string
}
```

#### Responses

- 200 Successful Response

`application/json`

```typescript
{
  detail?: string
}
```

- 422 Validation Error

`application/json`

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

## References

### #/components/schemas/DomainList

```typescript
{
  domains?: integer[]
}
```

### #/components/schemas/ForgotPasswordPayload

```typescript
{
  username: string
}
```

### #/components/schemas/ForgotUsernamePayload

```typescript
{
  email: string
}
```

### #/components/schemas/HTTPValidationError

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

### #/components/schemas/Message

```typescript
{
  detail?: string
}
```

### #/components/schemas/ResetPasswordPayload

```typescript
{
  token: string
  new_password: string
}
```

### #/components/schemas/StatusMsg

```typescript
{
  status?: string
  service_name?: string
}
```

### #/components/schemas/ValidationError

```typescript
{
  loc?: Partial(string) & Partial(integer)[]
  msg: string
  type: string
}
```
