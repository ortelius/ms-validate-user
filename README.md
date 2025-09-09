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

| Method | Path                                         | Description  |
|--------|----------------------------------------------|--------------|
| GET    | [/health](#gethealth)                        | Health       |
| GET    | [/msapi/validateuser](#getmsapivalidateuser) | Validateuser |

## Reference Table

| Name                | Path                                                                              | Description |
|---------------------|-----------------------------------------------------------------------------------|-------------|
| DomainList          | [#/components/schemas/DomainList](#componentsschemasdomainlist)                   |             |
| HTTPValidationError | [#/components/schemas/HTTPValidationError](#componentsschemashttpvalidationerror) |             |
| StatusMsg           | [#/components/schemas/StatusMsg](#componentsschemasstatusmsg)                     |             |
| ValidationError     | [#/components/schemas/ValidationError](#componentsschemasvalidationerror)         |             |

## Path Details

***

### [GET]/health

- Summary
Health

- Description
This health check end point used by Kubernetes

#### Responses

- 200 Successful Response

`application/json`

```ts
{
  status?: string
  service_name?: string
}
```

***

### [GET]/msapi/validateuser

- Summary
Validateuser

#### Parameters(Query)

```ts
domains?: Partial(string) & Partial(null)
```

#### Responses

- 200 Successful Response

`application/json`

```ts
{
  domains?: integer[]
}
```

- 422 Validation Error

`application/json`

```ts
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

```ts
{
  domains?: integer[]
}
```

### #/components/schemas/HTTPValidationError

```ts
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
  }[]
}
```

### #/components/schemas/StatusMsg

```ts
{
  status?: string
  service_name?: string
}
```

### #/components/schemas/ValidationError

```ts
{
  loc?: Partial(string) & Partial(integer)[]
  msg: string
  type: string
}
```
